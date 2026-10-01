# R4.0-003 可复用业务 Action：独立功能测试

## 需求、范围与非目标

- 权威需求：[requirements-v4.0.md](../../requirements/requirements-v4.0.md) R4.0-003 F1—F6、A1—A10，继承 R4.0-002 共享身份和 R3.0-004 不可区分授权合同。
- 本方案复用主 Agent 提供的普通 Entity + `semantic_definition`、`action_definition`、`parameter_definition` 注释方案，资源引用经普通关系，Operation 使用既有外部能力合同。独立业务输入和断言不复用开发候选。
- 覆盖候选、Protocol、Batch dry-run/apply_atomic、RDF、既有治理读回及有限相邻回归。图书馆设备移交/登记是测试数据，不成为平台业务概念。
- 不改产品实现、开发测试和需求，不重启服务、不提交；临时探针只调用现有合同。无 LLM、无 semantic modeling start、无外部业务调用，不验证 004 实际绑定、005 脚本、007 自动兼容或 011 接口字段映射。
- A10 真实建模和独立语义验收未获授权，本次 BLOCKED（解除条件：用户统一授权）；不得据 fixture 功能测试标记整体语义 PASS。
- 本文是唯一测试方案和轮次文档，复测追加记录，保留此前结果。

## 环境与前置条件

1. 工作区 `/home/yangxiang/ontology-platform`；主 Agent 确认 development-ready、所需开发回归通过、service 已重启且端点健康后才执行运行测试。
2. 使用 `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4003_independent_probe.py`；实际 HTTP 为 `127.0.0.1:8001/api`，依赖当前 PostgreSQL 和 Oxigraph。不打印 API key 或其他凭证。
3. 复用既有临时 Project/API key/lease/清理模式，自建业务输入与断言。新资源全部属于独立随机前缀，finally 删除 Project、API key、自有 registry/state/revision/graph set/audit 和 Named Graph，验证不存在。清理失败单独报告，不能隐藏在功能成功中。
4. 每轮记录 HEAD/工作区状态、命令、实际断言、HTTP/RDF 证据和清理。开发代码变化后仅复测受影响项和必要回归。

## 用例、步骤与通过标准

| 编号 | 条款 | 独立输入与步骤 | 期望与通过标准 |
| --- | --- | --- | --- |
| T01 | A1/F1 | 无 Operation 的人工设备移交 Action；两个流程引用同一动作；另一个同名但不同义动作 | 行为说明及 I/O 注释写读成功，无虚假 Operation 字段；两个流程指向同一 IRI；同名不同义不合并 |
| T02 | A2/F2 | 正式设备父类、特殊设备子类、多分类定义、无 Class 借阅对象；共同条件及子类局部条件 | 明确对象/类型关系和两层条件都可读；无 Class 对象保持空分类；不自动建立状态 Class、不写执行许可 |
| T03 | A3/F2 | 例外说明限定明确业务范围；多分类下两个冲突限制 | 例外范围/共享条件保留且不自动覆盖；冲突说明和相关范围同时可读、不选宽松条件 |
| T04 | A4/F3 | 保留登记、待合并登记均引用同一对象定义，单值与集合；输出为保留输入的更新结果 | 两个输入 IRI 不同；参数 direction/value_kind/required/cardinality 可读；对象及结果输入引用可解析；无实际业务行 |
| T05 | A5/F3 | 无业务输入、无输出、有条件的输出、输出未知、未说明输出；计算值参数有单位/枚举/缺失说明，新对象输出 | none/unknown/omission 分别保留；输出出现条件/result_kind/单位/枚举/缺失含义可读；无输出动作仍有预期效果 |
| T06 | A6/F4 | 条件→参数/属性/共享规则；成功、拒绝及未知效果；负责/审核角色和局部职责 | 自然语言范围及显式关联读回；效果仅为定义、不推进状态；职责不新增 Key Grant/Protection Set；未知不变成已发生 |
| T07 | A7/F5 | Action 关联零/两个 Operation，Operation 被两个动作共用；能力部分步骤和未确认对应；删除并更换关联 | Operation 与 Action IRI 分别识别；关联含义、范围、缺口可读，不默认等价/顺序；关联变化保留共享动作所有说明；活动 Operation 无绑定仍被拒绝 |
| T08 | A8/F6 | 隐藏参数/规则/Operation，Action 仍可见；先记录同一 IRI 不存在时响应，再保护精确读取；宽读取分页 | 受保护/不存在 HTTP 状态及 JSON 一致；实体/关系读取无隐藏 IRI 或名称；过滤在已实现的 limit/count 前；不虚构当前入口不支持的 offset/cursor，授权可见 Action 不被判为无约束；IRI 过滤不被声称能检测文本泄露 |
| T09 | A9/F6 | 完整独立候选→回执→二次确定性翻译→各阶段 dry-run/apply/幂等回放；错误字段/未知引用/非法 Operation 修正继续；相邻回归 | 全部身份、注释和关系保存；畸形输入给出准确反馈，修正能继续；不写不完整内容、不新增 Evidence；原子/授权/Operation 既有合同无回归 |
| T10 | A10 | 后续统一获准资料和真实建模产物的独立语义审查 | 本次未授权/未执行；功能 PASS 不能替代资料忠实度或真实建模质量 |

总体功能 PASS 要求 T01—T09 有实际适用路径证据且无未解决产品缺陷，清理通过；未执行或依赖不可用记 BLOCKED。相邻既有测试是回归证据，独立候选和断言是本次功能判定依据。A10 未完成时整体需求语义状态保持 PARTIAL。

## 测试轮次

### 第 1 轮：独立候选入口验证（2026-10-01，18:10:47 +08 重启后）

- 基线：`d03443de47407ed9f6f137ac973cc16f3db680d5` 加本轮 R4.0-003 未提交增量；主 Agent 已确认 development-ready，后端 full 1027 PASS/38 既有 SKIP、相关组合 50 PASS/3 subtests PASS。主 Agent 已重启，systemd active、8001 health ok、5173 HTTP 200。开发回归与独立验收分开记录。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4003_independent_probe.py > /tmp/r4003-independent-round1.log 2>&1`。
- 资源标识：`r4003-ab9d62283599487eb1a8e6431e8b7bde`；在正式候选回执前拒绝，0 断言、未创建 Project/API key/Graph，finally 清理验证通过。
- 实际结果：fixture 将业务角色 Entity 和角色关系 predicate 的 item_id 同时命名 `role`，入口准确返回 `ProtocolRetrievalFallbackError: neutral candidate item IDs are duplicated`。这是测试候选身份错误，产品无缺陷；只将自有 predicate item_id 加前缀，不改变业务参数、含义或既定方案。
- 结论：T01—T09 尚未完成，BLOCKED（fixture 已修正，进入同方案下一轮）；A10 未授权/未执行。证据 `/tmp/r4003-independent-round1.log` 与 `/tmp/r4003-independent-result-r4003-ab9d62283599487eb1a8e6431e8b7bde.json`。


### 第 2 轮：四阶段写入后读回参数修正（2026-10-01）

- 基线及业务输入与第 1 轮相同，重复 item_id 已 FIXED；命令使用同一探针，日志 `/tmp/r4003-independent-round2.log`。
- 标识 `r4003-a7cb57d23abb4e6ea69fdd9677d1aeb1`，23 个已执行断言 PASS：候选回执/确定性翻译、五类非法注释反馈、未解析引用/修正重试、精确不存在资源 404、Class/Property/Entity（含 Operation）/Relation 四阶段 dry-run/apply_atomic/幂等重放。
- 读回尚未完成：探针请求 read-model `limit=5000`，正式接口上限 2000，准确返回 422 `Input should be less than or equal to 2000`。这是探针参数错误，产品无缺陷；将临时探针上限改为 2000，足以覆盖本次不足千条的限定 fixture。
- 自有 Project/API keys/Named Graph 完整清理 PASS，`cleanup: true`。T01—T09 最终读回、授权/分页及相邻回归未完成，BLOCKED；A10 未授权/未执行，整体 PARTIAL。证据 JSON `/tmp/r4003-independent-result-r4003-a7cb57d23abb4e6ea69fdd9677d1aeb1.json`。


### 第 3 轮：结构化读回与边界（2026-10-01）

- 第 2 轮错误 limit 已 FIXED；基线与业务输入不变，使用同一独立 Probe，日志 `/tmp/r4003-independent-round3.log`，标识 `r4003-c9f9a100b102445f9dd09c4453dc93a6`。
- 已执行 249 项断言 PASS：各实体精确和列表注释逐字段相等；同名独立身份、共享动作引用、零/多 Class、Class 子类关系；结构化参数及结果与输入引用；none/unknown/omission、新对象/计算值、单位/枚举/缺失含义；全部共同/局部/例外/冲突条件、效果、职责及外部关联可读；Operation 定义通过治理 export 保留自身绑定/目标 Class；职责不新增权限、效果不产生业务状态事实、无 Evidence；非法活动 Operation dry-run/atomic apply 均 validation_failed、版本不变，修正后成功；注释 null 清除/恢复不影响共同说明。
- 尚未完成：A7 关联变更和 A8 授权过滤。探针把同主语同谓词的 delete/create 放入一个 Batch，dry-run validation_failed。既有 `modeling_batches.py` 的 `_effects_overlap` / `conflicting_item_effects` 将该对视为冲突；本需求不要求一个 Batch 内替换，下一轮按现有合同拆为 unlink 与 link 两个确定性 Batch，不请求扩大产品修改。本轮失败响应未完整保存 findings，故不把该响应归为已证实的产品缺陷。
- 清理 PASS，`cleanup: true`；Project/API keys/全部自有 Named Graph 不存在，证据 `/tmp/r4003-independent-result-r4003-c9f9a100b102445f9dd09c4453dc93a6.json`。
- 主 Agent 同时发现并准备修复 canonical 注释 subject 边界：创建 Entity 本体忽略 payload.entity_iri，而新注释曾优先采用它。本轮候选没有提供 entity_iri，已通过路径不受此问题影响；不能把当前基线当最终 PASS。等修复重启后，复用本轮既有成功证据，只执行未完成 T07/T08、canonical 独立边界和必要相邻回归。
- 本轮结论：已执行范围 PASS；未完成范围 BLOCKED（等待修复重启并继续），无本轮独立发现的产品缺陷。A10 未授权/未执行，整体 PARTIAL。


### 第 4 轮：最终重启后的定向复测与功能判定（2026-10-01，18:18:05 +08 重启后）

- 基线：`993efbeb7a51753a7a3c3a15d67e14d11d4a8bd1` 加 R4.0-003 未提交增量；HEAD 的新增提交为外部 R4.0-004 文档，不涉及本轮产品代码。主 Agent 确认产品冻结，canonical 修复让 Action/Parameter 及 Entity 共同说明都跟随实际 compiled Entity IRI。最新开发全量后端 1028 PASS/38 既有 SKIP（119.85 秒）、相关 Team 58 PASS/18 subtests PASS；Team 全量 2030 PASS/1 既有 SKIP/314 subtests PASS 在该小修复前完成，未把它当作修复后的全量结果。主 Agent 最终重启后 systemd active、8001 health ok、5173 HTTP 200。
- 按同一测试方案复用第 3 轮未受影响的 249 项成功证据，定向继续 T07/T08，并复测 canonical 边界及有限相邻回归；未重复全部独立业务断言、未修改产品实现。
- 独立临时 fixture 标识 `r4003-8655eb9d93fc4f838e85856b162ae2eb`；继续探针使用同一候选重建已清理的自有资源，四阶段 dry-run/apply/幂等回放以及解除/新增关联两 Batch 均成功。

实际命令：

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4003_remaining_probe.py > /tmp/r4003-independent-round4.log 2>&1
env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4003_canonical_probe.py > /tmp/r4003-independent-canonical.log 2>&1
env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run pytest -q   tests/test_r4003_action_semantics.py   tests/test_r4002_multiview_semantics.py   tests/test_operation_semantics.py   tests/test_semantic_access_authorization.py   tests/test_r3009_unified_semantic_graph.py   tests/test_modeling_batches_service.py::test_atomic_validation_failure_does_not_apply_any_item   tests/test_modeling_batches_service.py::test_recovery_observes_applied_rdf_and_finalizes_without_rewriting   tests/test_modeling_batches_service.py::test_bounded_recovery_can_fail_when_no_side_effects_are_proven   ../modeling_team/tests/test_r4003_action_contract.py   ../modeling_team/tests/test_r4002_semantic_definition_contract.py   --tb=short > /tmp/r4003-independent-regression.log 2>&1
```

- 定向真实依赖探针：41 断言 PASS、退出码 0；关联解除/新增保持 Action IRI 和所有 properties 完全一致，关系读回准确。
- 权限：隐藏参数/共享规则/Operation 后，精确读取与同一 IRI 未创建时的状态/JSON 完全一致；entity-list、entity-relations、statement-list 的可见结果等于独立剔除隐藏引用后的预期集合，limit=1 的首条和 visible_count 与可见集合一致；响应无隐藏 IRI/受限参数或规则名称。Action 的可见说明保持原值；治理 export 也无受限 Operation/参数/规则 IRI 及关系。精确资源入口本来不把 Operation 当普通 Entity 投影，Operation 的授权存在性验证由治理 statement/export 补足，不声称新增 Operation 详情路由。
- canonical 独立探针：6 断言 PASS、退出码 0，无存储写入。分别给 create_entity 提供不同于实际 entity_id 的多余 entity_iri，核对 semantic_definition/action_definition/parameter_definition 与本体全部落在实际 canonical Entity ；再核对 update_entity 的插入/删除跟随既有明确 IRI。开发方报告的边界修复已 FIXED，没有残留错目标注释。
- 有限相邻回归：68 PASS（11.31 秒）、退出码 0，无新增 skip/xfail；既有 FastAPI/Starlette/RDFLib deprecation warnings。覆盖新合同、共享声明、零/多 Class、授权、Operation 校验、atomic 验证失败无写入、已发生 RDF 写入恢复、无副作用时有界失败。相邻回归用于守住既有合同，独立功能结论仍来自自有输入和断言。
- 清理 PASS，`cleanup: true`：Project/API keys 不存在、全部自有 Named Graph 已删除并确认不存在；所有前轮也清理成功，没有新增业务行、真实凭证或外部调用。证据 JSON `/tmp/r4003-independent-result-r4003-8655eb9d93fc4f838e85856b162ae2eb.json`。

| 用例 | 第 4 轮状态 | 判定与证据 |
| --- | --- | --- |
| T01/A1 | PASS | 复用第 3 轮：人工清点无 Operation 关联也有效，两个流程引用同一 Action IRI，同名不同义保持独立；当前 canonical 有限回归通过 |
| T02/A2 | PASS | 复用第 3 轮：正式 Class 关系、子类关系、零/多 Class、共同与局部条件全部明确读回；当前统一图相邻回归通过 |
| T03/A3 | PASS | 复用第 3 轮：应急例外具有范围，共同条件未覆盖；多分类的两项限制和冲突说明均可读，不要求平台推断文本矛盾 |
| T04/A4 | PASS | 复用第 3 轮：同类两个输入身份不同、scalar/collection 明确、updated_input 与保留输入显式关联，无额外实际业务对象行 |
| T05/A5 | PASS | 复用第 3 轮：none/unknown/omission 区分、新对象/计算值/出现条件/单位/枚举/缺失含义保留，无返回值仍有预期效果 |
| T06/A6 | PASS | 复用第 3 轮：条件与参数/属性/规则、成功/拒绝/未知效果、局部职责及角色可读，无状态事实/Grant/Protection Set 副作用 |
| T07/A7 | FIXED/PASS | 第 3 轮 fixture 同 Batch 冲突已按既有合同拆分，两个实际 Batch 均成功；Action 身份/说明完全不变，解除/新增关系准确；多能力/共享能力/Operation 自身约束复用第 3 轮 |
| T08/A8 | PASS | 新执行精确不可区分、隐藏端点/关联无泄露、过滤先于 limit/count、Action 保留和治理 export；不声称 IRI 过滤自动扫描文本或覆盖不存在的 offset/cursor 接口 |
| T09/A9 | FIXED/PASS | 四阶段 Protocol/Batch 当前环境写读成功；null 清除/恢复、畸形注释/未解析引用及修正复用第 3 轮，canonical 新边界 PASS，68 相邻回归 PASS；无 Evidence 补证任务 |
| T10/A10 | BLOCKED | 未授权、未执行真实建模或独立资料语义验收；解除条件为用户后续统一授权，不能用本次功能证据替代 |

最终结论：**A1—A9 独立功能测试 PASS，无未解决产品缺陷，无需开发修复后再做功能复测。A10 未授权/未执行，整体需求真实语义验收保持 PARTIAL。** 服务重启由主 Agent 执行和验证；本 Agent 未重启、未提交、未改产品实现或开发测试。前轮 fixture 错误完整保留，不计为产品缺陷。
