# R4.3-025 独立设计验收记录

## 授权与证据边界

用户2026-10-15要求“请细化并设计R4.3-025需求，通过独立验收”。本轮交付为需求细化、
详细设计及独立**设计**验收，不实施代码／活跃合同，不启动服务、调用provider、修改
模型或恢复生产；建模轮次／额度不变。A1—A10均未执行，不以设计PASS推导025工程、
024实际Modeling采用／自查或最终独立语义质量／提速已验证。

- 权威条目：[R4.3-025](../../requirements/requirements-v4.3.md#r4-3-025)。
- 设计：[模型变更的确定性转换与执行](../designs/2026-10-15-r4-3-025-deterministic-model-execution-design.md)。
- 开始代码基线：`fc8be76`，024设计已通过，但未实施。
- 无关未跟踪`docs/presentations/`、`slide-deck/`保留。
- 期间其他任务修改`modeling_team/modeling_readonly.py`、`read_proxy_mcp.py`及其测试；
  本轮不修改、验证、提交这些代码，不把并行改动当本设计的已交付依赖。

## Round 1 — PASS

独立Reviewer：`/root/r4325_design_review`，`plan_reviewer` Agent，非需求／设计作者。
只读审阅，不修改文件，不运行产品测试／服务／模型调用，不参与生产证据生成或修复。

最终主输入SHA256（PASS后状态同步前；Reviewer再次核对无变化）：

| 输入 | SHA256 |
| --- | --- |
| `docs/requirements/requirements-v4.3.md` | `633d7927632a8ee11c01b3a1533efd0150b750536886afc9009cd5ca82d8a3f7` |
| `docs/delivery/designs/2026-10-15-r4-3-025-deterministic-model-execution-design.md` | `66f81ee794a4c569408fc30136cb6f4ca3a1c03c9d379b72d89977caf76bb682` |

完整审阅025设计第1—7节、权威F1—F7／D1—D8／A1—A10、024设计和独立验收边界、
003及适用AGENTS。结论：**PASS；Critical 0、High 0；关键未决假设：无。**

Reviewer实际定向核对源码／合同：

- `modeling_team/staged_decisions.py`、`references/r3-0-009-unified-graph-contract.json`、
  `references/modeling-batch-item-contract.json`、`protocol_mechanics.py`：统一图弱内层
  校验、旧转换与绑定helper的格式限制准确，设计没有冒用旧能力。
- `modeling_team/runner.py`、`capability_mcp.py`、`staged_batch_write_forwarder.py`和
  `backend/app/services/build_sessions.py`：真实task／scope／Session／lease有现有落点，
  intent／receipt／恢复复用边界明确，未把旧dry-run／翻译门带进新核心。
- `backend/app/services/modeling_batches.py`、`modeling_handlers.py`、
  `semantic_command_compiler.py`、`semantic_export.py`及`backend/app/core/config.py`：
  outputs_for和显式程序ID可用，Batch递归item-output引用与单批apply_atomic可用；
  设计保留跨批成功、依赖停止和未知结果原身份对账，不承诺全局事务。持久身份、
  source map、Finding及实际revision／索引状态区分符合核心要求。

Reviewer没有GitNexus图分析，不宣称图影响覆盖。024实际工具接入、025工程、真实建模
及独立最终语义验收保留未完成，不受并行读取代理修改影响。

## PASS后同步与文档验证

PASS后只同步需求顶部／总表／025状态和024依赖进度、设计第7节、tracker025及关联进度、
本记录；未改变需求F1—F7／D1—D8／A1—A10或设计第1—6节。状态同步后的整文件摘要
不冒称上表审阅原件，不需要无新增实质变化的重复审阅。

本地链接／锚点、Markdown围栏／表格、F／D／A连续编号、源码路径及`git diff --check`
通过。仅本次四份文档纳入提交，产品代码和活跃Skill未变，本轮不需backend／frontend
测试、Skill validator或服务重启。文档检查只证明文档一致与可导航；独立设计PASS只
证明当前方案可交接实施，不证明执行、业务或性能结果。

## Round 2 — 用户后续边界对齐 PASS

用户后续明确compiler返回依赖有序ontology batches与source_map，item保留稳定
client_item_id（candidate identity）、可选change_id、resource_kind和JSON Pointer，
不带Session／lease／revision／idempotency／资源技术ID；并指定DirectModelExecutor
构造签名及execute(batches, source_map)职责。本轮按此新增需求D9、设计§3.3，同步
F1／F3／A1及编译／执行分工，原Round 1审阅摘要和结论保留。

只改四份025文档，不接管工作区并行backend／Runner／读取代理等实现。本轮开始时checkout
尚无compiler或DirectModelExecutor实现；审阅后并行任务新建并持续编辑
`modeling_team/direct_modeling.py`和`direct_execution.py`。本次为设计合同对齐，不提交
这些他人未跟踪实现，不宣称输出代码已对齐。定向读取发现compiler当时仍使用change_id
作client_item_id，属于待联调差异，不能据设计PASS关闭。
原独立Reviewer完整复核当前F1—F7／D1—D9／A1—A10与设计第1—7节，结果为
**Round 2 PASS，Critical 0、High 0、关键未决假设无**。

审阅中Reviewer指出固定submit／read转发本身不能承担Session／lease生命周期调用，
作者在§3.3明确scope承载既有可信生命周期adapter，写／读转发职责不变；Reviewer随后
以最终输入确认接口闭合。该澄清在PASS前完成，没有增加构造参数或新生命周期框架。

最终审阅主输入SHA256（PASS后状态同步前）：

| 输入 | SHA256 |
| --- | --- |
| `docs/requirements/requirements-v4.3.md` | `8ce1fcf239162ee750b6414f55adff97fcc785fd9f0917f1a46d35087746a9b2` |
| `docs/delivery/designs/2026-10-15-r4-3-025-deterministic-model-execution-design.md` | `659b69bb2cd5676287d69b9fdc9a3e28407c72ccbe591746421e8d7500648bdf` |

核对依据：§3.3保留ontology_id及稳定来源ID，一项多命令按批次定位；source_map以
(batch_index, client_item_id)对应artifact及字段JSON Pointer，sidecar不透传封闭后端
schema。Executor填执行身份／真实绑定并保存intent／receipt／apply Attempt proof；
proof不恢复dry-run门。§5的单批原子、跨批成功保留、持久去重、未知结果对账及真实
revision／索引边界保持；与原024／最终独立语义验收分工无回退。

PASS后仅同步需求／设计／tracker状态及本记录，未改本次合同。文档链接／锚点、围栏、
F／D／A编号及diff检查通过；不运行产品测试／服务。独立结论只证明设计通过。

## Round 3 — Executor实际消费合同对齐 PASS

用户后续明确resource_kind必需、change_id可选、client_item_id保持；sidecar在平台投影
剥离；source_map采用str(batch_index)→client_item_id→entry嵌套结构，field_map为
payload JSON Pointer到候选／请求指针列表。cross_batch_dependencies／depends_on_batches
只阻断未成功依赖，Executor不解释target_ref／item_ref／IRI。准确capability入口为
modeling_submit_model_changes(modeling_id, request)，随后execute(batches, source_map)。

本轮据此同步需求F3／F4／D9／A4与设计§3.1／3.3／4.3，明确跨批真实输出由Runner
能力层在执行前绑定；新输出未存在时沿既有阶段取得真实成功回执，再准备后续阶段。
同批合法item_ref归后端Batch请求内解析，Executor仅投影。成功阶段不重放，失败／未知
依赖不得删边绕过。原Round 1／2结论及摘要保留；同一独立Reviewer完整复核当前需求及设计，结论
**Round 3 PASS，Critical 0、High 0、关键未决假设无**。

最终主输入SHA256（状态同步前）：

| 输入 | SHA256 |
| --- | --- |
| `docs/requirements/requirements-v4.3.md` | `02a5cb1796b84a51c8345ce528758ab7f2113e69002304e1d7fc649a40c4c59f` |
| `docs/delivery/designs/2026-10-15-r4-3-025-deterministic-model-execution-design.md` | `36705665eff4ffc7f90fc27df9b58d450e097a161f50322bbe4f1a9994b69644` |

Reviewer确认准确能力入口、稳定ID／嵌套映射、能力层执行前绑定及真实回执后续阶段、
Executor只阻断依赖及后端同批解析的责任闭合。单批原子、持久幂等、成功不重放及未知
先对账保持；无原设计范围回退。PASS后仅同步状态及本记录，独立结论仍限设计。
文档144处本地链接／锚点、围栏／表格、F1—F7／D1—D9／A1—A10编号及diff检查通过。

只读核对并行实现的当前切片：direct_modeling.py现已保留candidate identity并生成嵌套
source_map，Round 2记录的旧ID差异已消除；direct_execution.py有sidecar剥离及依赖状态
阻断；Runner有准确capability→compiler→execute调用。但是compiler仍可能输出跨批
item_ref，能力层实际绑定／分阶段执行尚待集成验证，不能从排序或入口存在判定通过。
本轮不接管、测试或提交这些持续变动中的并行代码，仅提交025的四份文档。
