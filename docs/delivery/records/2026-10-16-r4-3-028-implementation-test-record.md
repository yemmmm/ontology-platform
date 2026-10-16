# R4.3-028 实现与工程验证记录

权威范围：[需求](../../requirements/requirements-v4.3.md#r4-3-028)，
[独立设计 Round 3 PASS 的设计](../designs/2026-10-16-r4-3-028-incremental-model-awareness-design.md)。
本轮用户明确要求完成028实现；沿已确认D1—D13实施，不新增真实建模／修模轮次，
不恢复生产或验收、不改变模型／effort，也不改写历史run及其证据。

当前结论：**工程实现、适用开发回归及服务重启检查完成；真实增量语义质量与净效率待验证**。
工程集成使用SQLite和真实rdflib Dataset，调用实际compiler、Modeling Batch、Session、
租约、治理读取及Ontology更新服务；不是生产PostgreSQL／Oxigraph或真实Agent语义验收。

## 实现

- 将写入前的状态／有限概览、跨获准图多表达式发现、按实际IRI完整补读、语义比较和
  复用／创建连接／修改／澄清方法放到完整及最小链实际required Skill，角色instructions
  保留短指引。同步029 Task、实际_task_text、直接写入合同和读工具说明；不改变小链
  业务范围、不增加全图读取、固定搜索次数或审批门。保留重要候选理由和未知到既有note。
- `SemanticNamespace.resource_identifier`使用当前Settings原生前缀、严格UTF-8解码和
  原resource编码的逐字往返；namespace段来自原CREATE_RESOURCES表。ObservedModelBindings
  在本run观察、摘要、scope、revision、当前可读及full RDF类型核对后恢复原生执行身份。
  成功回执仍走原路径；外部IRI不猜ID，支持IRI的字段仍可使用，ID缺口返回明确反馈。
  当前full读取期间的修订漂移也返回可修正冲突。
- 可选能力参数placement_ref引用Host应用确认拓扑后冻结的本run快照条目，通知含真实
  归属和slice。字段不进入原六字段change／fields；核对当前plan、快照和scope，拒绝
  与candidate／target真实归属冲突。归属和确认plan身份进入原submission快照／查重；
  换归属不复用另一图的计划，也不能绕过原未知写入fence。省略placement_ref、由candidate
  slice自动定位时仍绑定确认拓扑摘要；历史无此字段的保留计划兼容原重试。旧单图调用兼容。
- 029准备时固定绑定默认`from_slice_depends_on_to_slice`，显式反方向只允许原另一个
  枚举；不从自由文本猜方向。compiler原source_map保留实际已绑定引用及原字段路径。
  直接Mapping提交在编译后、首次apply前核对owner当前引用；缺失时按当前确认依赖
  接原引用准备能力，只处理受影响owner，与当前引用取并集。PATCH响应丢失读回原
  目标，未应用则返回mapping_reference_scope_required，允许同run更正／重试。
  普通跨图relation_type不增加Mapping门。
- 同步[MCP合同说明](../../reference/mcp.md)。无UI、数据库schema或平台REST新增。

## 影响检查与验证

GitNexus impact查询ObservedModelBindings、_direct_ontology_placement和
apply_mapping_reference_ontologies均为Target not found；索引缺少这些新符号，未重建索引。
本轮定向检查了Runner能力入口／确认拓扑通知、compiler引用／source_map、原执行器查重
与未知写入fence、scope Mapping激活及029准备调用点。detect_changes报告medium、3条
历史namespace相关流程，但映射含旧符号／位置，不能宣称覆盖当前新增跨模块路径。

有界工程验证覆盖：

- 无旧run回执的原生Class经Context Query／固定读模型实际读取后绑定ID，创建关系并
  检查实际RDF domain／range及治理读取；percent编码／外部namespace／非canonical、
  类型冲突、伪造引用、旧revision及同目标刷新后继续。另覆盖CQ宽分类不替代full RDF
  类型：原生ObjectProperty的property／relation_type和SemanticMapping身份正确恢复，
  外部自定义类型资源保留原有IRI字段能力，不因本次ID恢复而强制复制或拒绝。
- 两个已有图fields-only显式选归属、相同请求不同图各执行一次／原图重试不重放；
  省略、假引用、plan绑定漂移、target归属冲突及换归属不能绕过原uncertain。另覆盖
  省略placement_ref但Host确认拓扑变化的同candidate请求，实际写到新归属而非复用错图旧计划。
- 跨图普通relation_type不要求Mapping方向／配置；跨图TableMapping目标可读但配置
  未准备时不写入，开门后确认依赖可同run成功；正反两个方向、保留owner旧O3引用、
  不改其他owner、PATCH未应用后重试及已应用响应丢失后读回、历史Task缺方向的定位反馈。
- 029新任务无Mapping时省略方向仍固定默认；显式反向透传，null／未知枚举拒绝。
  实际完整／最小包required Skill加载、任务scope／方向提示和工具可选参数检查。
- 原六字段输入、乱序回执绑定、失败无写入、跨批依赖及未知写入对账沿原测试回归。

已完成的结果（运行命令均从backend目录执行）：

| 检查 | 命令及结果 |
| --- | --- |
| Team全量复测 | `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short`：3082 passed、12 skipped、318 subtests passed，295.52秒 |
| 当前直接路径相关回归 | `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_incremental_model_awareness.py tests/test_direct_modeling_team_edges.py tests/test_direct_modeling_team_integration.py ../modeling_team/tests/test_direct_submission.py ../modeling_team/tests/test_direct_modeling.py ../modeling_team/tests/test_direct_modeling_wiring.py ../modeling_team/tests/test_r4010_mapping_contract.py ../modeling_team/tests/test_r4029_incremental.py ../modeling_team/tests/test_r4029_independent_acceptance.py ../modeling_team/tests/test_r4326_minimal_chain.py ../modeling_team/tests/test_workbench_platform_binding.py -q --tb=short --disable-warnings`：164 passed，87.12秒；包括最后Class槽位约束和自动定位的拓扑去重修订 |
| 最后类型槽位补测 | 上项后对source／target／parent Class ID引用补齐实际class类型约束；重跑`tests/test_incremental_model_awareness.py ../modeling_team/tests/test_direct_modeling.py`：62 passed，47.17秒。新增36项专项（含参数化）及26项原compiler测试覆盖当前最后代码；已有实例不能作为概念端点，错误不进入Batch |
| 后端全量 | `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short`：1260 passed、56 skipped，1034.52秒；完整日志保留 |
| 格式／合同 | 两份Skill quick_validate、变更JSON／YAML、文档链接和git diff --check通过；无UI代码变更，不要求前端suite |
| 运行重启 | 全量通过后执行`systemctl --user restart ontology-platform.service`；2026-10-16 17:56:21 +08重启，unit active，`curl --fail`核验8001/api/health返回`status=ok`、5173/返回HTTP 200 |

可读原始日志保存在gitignored目录`workspaces/verification/r4-3-028/`。保留失败轮记录，
不以末轮覆盖前轮。后端首轮发现旧断言后中断，修订后重新执行全量；Team全量复测后，
当前绑定分类及Class槽位、拓扑去重的最后调整统一由末轮164项定向回归覆盖，不把早先
全量记录称为这些后续代码的逐项全量重跑。

第一轮相关旧测试替身缺少GET owner元数据响应，已按实际合同更新。后端全量首轮另
发现基线旧测试仍期待unsupported语义字段到apply才失败；基线compiler已提前拒绝该
字段。本轮将断言改为检查准确unsupported_semantic_field、原change／字段路径、零
Batch／Session及零写入；保留原子失败保护，未放宽生产校验。

Ruff相关新增代码通过；runner.py存在7条基线已有F401／F811／F841，使用`git show
HEAD:modeling_team/runner.py | ruff check --stdin-filename modeling_team/runner.py -`
确认相同问题，未顺带清理无关代码。两份修改Skill的quick_validate均通过。Team全量首轮另有一个使用__new__绕过初始化的
测试替身缺少_unified_graph；已在替身补上明确的非统一图模式，未为此增加生产兼容分支。

## 验收边界

以上是开发工程证据。A4／A10仅证明配置／挂载和提示面可达，不能证明新Agent真实采用；
A6—A10仍缺较大已有模型上的自主候选发现、同义复用、增量连接、受影响旧业务的独立
语义结果。A5缺同条件墙钟、首次正确率及用量对照，新指引也增加输入成本，净效率仍
待证。不以本次少量工程fixture替代大模型、不把设计或工程PASS扩成L1／净效率PASS。
