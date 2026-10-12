# R4.0-029 基于已有模型的增量建模设计

## 1. 权威范围与具体目标

权威范围：[R4.0-029](../../requirements/requirements-v4.0.md#r40-029-基于已有模型的增量建模)；
反馈场景由 [001](2026-10-12-r4-0-001-semantic-feedback-design.md) 提供输入。
本轮用户确认独立通用能力，授权细化与设计。决策主表保留在权威需求 D1—D8。
基线为 2026-10-12 checkout 440d534；尚未独立设计审阅、实施、功能或真实语义验收。

例：维修模型已有设备、工单及维修规则。用户新增备件采购目标和资料，新一轮需要
读取现有设备／工单，识别可复用定义，再建采购含义及真实跨业务关联。另一轮也可以
处理反馈中的错误规则，或补充原来未确认的口径。三种输入使用同一增量执行路径。

本轮修改的是当前获准模型，新增的是任务及运行身份。检查点恢复仍用于原目标未完成
工作；029 不借恢复旧 run 变更其已冻结目标，也不恢复模型内部对话或回滚数据库。

## 2. 已有入口与真实缺口

| 实际文件／合同 | 已有能力 | 029 所需的最小差异 |
| --- | --- | --- |
| [host_ops.start_run](../../../modeling_team/host_ops.py)、[DeliverySession](../../../modeling_team/delivery.py) | 新 run 启动、授权配置、模型路由、实际请求回执 | 新内部增量启动入口准备有界任务及现有范围；沿同一 Delivery／Host 启动链 |
| [PlatformScope](../../../modeling_team/platform_scope.py) | create／existing／checkpoint；existing 目前主要按单一 Project／Ontology 绑定 | 直接 existing 支持明确多 Ontology ID，复用归属、版本、Session／Lease／Attempt 检查 |
| PlatformScope.apply_ontology_plan、[Runner 拓扑接线](../../../modeling_team/runner.py) | 现有新建路径预建首本体、其余部分按名称匹配；已有 ontology_ids 会提前返回 | existing 增量按 ID 复用及按获准拓扑创建，不能靠同名绑定或提前返回跳过新计划 |
| [旧 existing Task](../../../modeling_team/tasks/r2-3-003-existing-scope-incremental.yaml) | 有界旧场景增量流程，固定 Start75、删除目标及特殊延续候选 | 仅复用底层能力；新 v4 Task 不继承旧 fixture、GraphSet、Evidence／推理和硬编码流程 |
| [unified 合同](../../../modeling_team/references/r3-0-009-unified-graph-contract.json)、[staged_decisions](../../../modeling_team/staged_decisions.py)、[protocol_mechanics](../../../modeling_team/protocol_mechanics.py) | 当前候选／批准／计划、existing identity binding、原子 Batch、read／receipt 绑定 | 补当前多本体已有定义的复用覆盖；按实际读绑定目标，复用条目不能转换为 create |
| [场景地图](../../../modeling_team/scenario_map.py)、R4.0-007／014 | 共享定义、维护责任、依赖、实际产物进度 | 从当前获准事实与可复用公开成果开始，加入本轮目标及影响范围；历史状态不直接提升为本轮 PASS |
| [checkpoint_recovery](../../../modeling_team/checkpoint_recovery.py)、R4.3-014 | 原目标恢复、写入对账、已完成内容不重放 | 保留为独立恢复路径；029 新目标默认不依赖历史检查点 |

已有代码只证明这些入口存在，未证明通用多本体增量流程已经工作。尤其需要验证现有
候选覆盖检查能否接受“只复用、不写入”的条目，及增量创建本体后是否正确保留作用域
与资源归属；不靠换 Task 名称宣称交付。

## 3. 内部入口与输入合同

首版由 modeling-dev-loop 宿主或同等可信内部 Host 发起，不向外部召回／反馈调用者开放
生产启动。拟增加以下 CLI 子命令，封装已有 Delivery 启动流程，不形成另一套监督器：

```text
python -m modeling_team incremental start --request workspaces/<本轮请求>.yaml
```

该命令尚未实现。内部请求描述本轮工作；业务用户不填写 run ID、Key、lease 或 Batch。
宿主为输入创建不可变请求快照，生成新的 Delivery 配置和新 run ID，返回请求／会话及
查询入口。相同 request_id 的未知启动先核对已有 launch／run，不能换 ID 盲重启。
范围不符、缺资料或缺运行授权返回可修正反馈，不能自动改目标或追加额度。

| 请求字段 | 合同 |
| --- | --- |
| request_id | 宿主生成的本轮启动 UUID；贯穿同次启动核对 |
| project_id、ontology_ids | 同一已有 Project 内明确、非空、不重复的模型 ID；至少一个既有本体 |
| objective | 本轮有界业务目标，例如新增备件采购或定位选定反馈；不是“自动优化到满意”为止 |
| approved_sources | 已获准业务资料／访谈／公开交接引用；有正文及有效来源，不挂整个仓库或旧运行目录 |
| feedback_ids | 可选；明确同 Project 的反馈 ID，不与 approved_sources 混成已确认业务事实 |
| profile、model_profile | 本轮已选角色和模型绑定；沿现有配置合同，不私自更换或强制固定角色数 |
| authorization_reference、valid_until、production_start_limit | 实际用户运行授权及期限／额度；仅登记、不以请求自己授权 |
| allow_new_ontologies | 默认 false；本轮授权是否允许在原 Project 内按业务拓扑创建本体 |
| acceptance_scope | 本轮新增／修改业务问题、关联问题和受影响旧问题的预期范围；CQ 审核后正式冻结 |

没有创建新 Ontology 的授权时，先在获准既有本体内组织新增业务；若业务判断确实需要
新本体，提出有来源的拓扑／范围决定并继续独立工作，不能私自创建或错误塞入现有本体。
新增业务不自动意味着增加 Ontology；平台检验归属和授权，不替 Modeling 判断拓扑。

新 Task 模板的拟定位置为 modeling_team/tasks/r4-0-029-existing-model-incremental.yaml。
宿主用模板和上述请求生成 schema_version=2 的正常 Task 快照：目标、获准 role_sources
及现有 multi_slice_workflow／staged_modeling_decisions／unified_semantic_graph／CQ selectors。
不要使用当前仅针对 formal R2.3-005 的 task_overlay 绕过正常合同。
本设计不要求改变后台全局角色配置，也不把旧 R2.3 固定 formal registry 当作合法性门。

## 4. Team 已停止后的具体启动顺序

1. 用户或内部 Host 提出本轮目标、资料和授权，例如“项目 P 继续新增备件采购”；反馈
   场景则先选 F1／F2，并说明处理目标。只提出需求或提交反馈不自动消耗 start。
2. Host 核对目标 Project／Ontology 归属、当前修订及旧写入／资源状态。已有 active writer、
   未知 Attempt 或未收敛写入沿既有通路处理；不能通过新 run 掩盖或绕过。
3. 生成本轮请求、Task 和 scope 文件；scope.mode=existing，绑定明确已有 ID。
   创建新的 Delivery session，填写实际获准 operations、资料、模型配置及授权引用。
4. 沿已有 delivery CLI 启动受管 Delivery，Delivery 调用 start_run 创建新生产 run 和
   当前 Profile 的新角色线程；返回启动接受不表示 semantic start，核对实际 semantic-start。
5. 新 run 新建 Build Session／Lease 和本轮凭据；旧已撤销 Key 不复活。旧模型、源 run、
   题集及报告保留；原 Team 是否存在不成为新任务的记忆依赖。
6. Protocol 读取当前获准模型，按现有协作／handoff 通道把必要业务定义、关系、修订及
   完整性说明交给 Modeling。以读取当前模型开始增量分析，不重演已应用历史批次。
7. 完成本轮生产、只读交接和独立验收，反馈场景再追加反馈处理结果；正常完成沿 028
   原地待命，显式 stop 才销毁。

宿主负责启动准备和权限绑定，Delivery 负责全程推进，Coordinator 负责场景／内部协调，
Modeling 负责业务含义，Protocol 负责身份、计划与写入，独立 Consumer／Judge 负责验收。
不把配置文件本身当作启动许可，也不让外部 Agent 的 feedback_id 请求直接开生产权限。

同一存活生产 run 内、仍属原已授权目标的修正继续原 run。已经封口的待命 Team 可以
解释反馈，但“继续”不会重新打开写门；本轮新增业务／新目标走上述新任务。若原 run
尚未完成而退出，使用 015／014 的检查点恢复，并保留其原目标与剩余工作。

## 5. 读取、增量与共享语义

### 5.1 当前模型是起点

Protocol 复用 get_project_build_context、get_modeling_context、获准 Ontology／资源 read model、
关系／事实读取及 query_semantic_context，取得当前目标范围的实际状态。业务分析从相关
定义及必要共享依赖开始，按缺口展开；不用整个模型导出或全面审计作为启动前置。
分页未取完、保护集限制、定义冲突及未知须传达，空结果不等于模型缺失。

已有场景地图／公开业务决定可按其来源和版本复用；发生变化时以当前获准模型读回为准，
资料冲突请求业务澄清。旧 Agent 全对话、隐藏 CQ／答案、Judge 私有理由不进入生产。
历史审批只有来源、含义、范围和内容仍有效时复用；其原身份和时点不改写为本轮批准。

### 5.2 本轮候选与目标绑定

候选明确表达复用、新增、修改及必要有依据的删除意图。优先使用现有 unified 中间表示：
为需要引用的既有定义保留对应候选条目及当前确认含义，新的 relation／参数等通过
definition_ref 引用该条目；Protocol 的 identity_bindings 从当前 read／receipt 绑定其
实际资源。Modeling 不猜 IRI，Protocol 不按名称单独判同义。

复用条目由有效已有身份及实际读取覆盖，不生成 create 命令或无意义 update。实施需
使 protocol_check_plan_coverage 等覆盖核对识别该已有绑定，仍检出未应用的新内容。
若本轮检查后全部无需模型改动，允许按实际读取及适用独立验证完成“无需改动”的任务，
生产交接覆盖以已有有效绑定证明，不为了满足非空写计划伪造一次 update／apply。
对模型内相关定义的新增／修改意图在当前候选及 Coordinator 审阅理由中明确，Protocol
计划的 command_kind 和目标必须对应这些批准内容；不得把“复用”翻译为删除／重建。
复用同一业务定义不增加同义节点；同名而含义不同保留区别。

实体／关系／属性及映射等资源继续使用已支持的普通业务语义和 Batch 命令；
实体 update、关系／事实修改与必要删除只选当前已声明命令，不创建并行补丁语言、
通用 diff 引擎或新的 delta 资源。若现有候选／命令不能忠实表达某个具体改动，返回准确
不支持内容，先作窄合同补齐；不能伪造成新增节点绕过。候选内容、原目标、现有读取和
明确意图共同纳入原审批绑定；仍保留原候选 schema，不在普通条目临时塞平台字段。

修改共享定义沿 007 读取直接引用及会影响解释的已知间接依赖，记录必要的本轮调整。
兼容修改保留身份，必要同步引用在现有可用原子 Batch 内共同修改；跨 Batch／Ontology
不宣称全局原子性。不能安全原位替换时沿 007 经业务确认建立新含义定义，再有序切换。
本期不增加同身份历史版本固定、自动合并／实体消歧或跨 Project 共享。

### 5.3 多 Ontology 绑定与新增

existing 输入使用 project_id＋ontology_ids；既有单 ontology_id 输入沿当前入口归一化。
均先按实际 ID 校验归属、当前修订和可用状态，不按名称找到“近似相同”的本体。
拓扑决定在现有 ontology_plan 中增加 existing 模式下的两种条目形态：

```json
[
  {"ontology_id": "existing-ontology-id", "slice_ids": ["repair", "parts"]},
  {"name": "另一个经批准的新业务本体", "slice_ids": ["approved-new-slice"]}
]
```

此为拟定合同示意。第一种明确复用获准 ID；第二种只在 allow_new_ontologies=true 且
当前拓扑批准成立时创建。两个字段形态互斥；缺 ID、失效 ID 或同名现有本体不自动转成
create／reuse。新建重试依本轮实际创建回执绑定，不依据名称复用别人的资源。
原 create 模式合同保持；增量 existing 分支不得使用“首项是预建本体”的假设，也不得
因为 ontology_ids 已初始化而提前返回、忽略后续合法计划。

所有模型及新建本体保留原 Project 归属。退出／失败清理只处理本轮凭据、Session／Lease
和获准临时资源；不得删除既有 Project／Ontology／模型。新增已写入资源在失败时也
保留并报告实际状态，不自动回滚；恢复使用 014 的实际完成覆盖及原请求对账。

## 6. 生产与验收合同

按当前 Task 组织本轮场景／拓扑、CQ 生成审核冻结、候选确认、dry-run、翻译审阅和 apply。
首期复用现有冻结及分阶段生产顺序，不把平台用来推理业务语义。CQ 覆盖新增／修改范围、
实际跨业务关联和受影响旧问题；未经重验的历史部分不提升为当前整项目 PASS。

旧冻结题集和报告原件不修改。本轮新的冻结题集和模型绑定明确其分母及验收范围；不把
旧报告拼到新报告来宣称全部通过，不通过删难题或缩范围消除本轮明确缺口。
反馈／修模公开问题属于公开回归，不能算作隐藏盲测。正式验收者只读当前受治理模型，
不读取生产材料替代语义证据，不创建、继续或修复被验收 run。

正常成功写入信任平台应用回执及版本确认，沿 R4.3-015 不追加逐批完整写入比对。
有明确业务目的的读取、关联自查、异常／未知写入对账及最终独立语义验收保留。
修订漂移重新读取受影响内容、重审／dry-run；未知 apply 先对账，不能换 Key 或 run 重放。

结果分别记录本轮复用／新增／修改／未完成内容、实际修订、应用结果、验收范围及独立
结论。反馈修正成功、新增业务通过及旧范围未重验须能区分；业务未知保持未知。
技术／平台／协作故障不推导业务模型质量失败，L0／L1／L2／L3 分层不变。

## 7. 实施交接与验证

| 责任面 | 应实现的范围 |
| --- | --- |
| modeling_team/__main__.py、host_ops／delivery 配置接线 | 内部 incremental start；准备、快照、实际授权及已有启动回执核对；没有第二个监督器 |
| 新 029 Task 模板、contracts.py、profiles／角色包与方法 | 正常 v4 Task／现有 Profile 复用、获准输入及当前模型增量职责；不继承旧 formal fixture 限制 |
| platform_scope.py、runner.py、scenario_map.py | 单／多 existing ID、现有模型读取、增量拓扑条目、创建回执、归属和保留清理 |
| staged_decisions.py、protocol_mechanics.py、能力说明及 unified 合同 | 复用条目与绑定覆盖、纯复核无需写入的收口、现有身份禁止 create、明确新增／修改意图的计划核对、受影响引用 |
| 001 反馈服务与 Delivery 内部读取 | 选定反馈的公开原文和状态投影，不放隐藏内容；处理结果引用新运行和验证 |
| skills/modeling-dev-loop 及现有 Team tests | 宿主启动指南、实际绑定、暂停／继续／待命边界、关键回归 |

先交付 029 通用增量入口，再接 001 内部反馈启动；001 外部采集可独立交付，不把 029
未交付变成禁止保存反馈的条件。两者使用同一业务流程及接口合同，不各建一个改进 Runner。
实现授权后按改动范围运行 Team 测试及后端／UI 必需检查；服务代码变更按仓库要求重启
并核对健康。上述是后续验证安排，本轮没有运行实现测试。

独立功能验收覆盖新 Team 接既有单／多本体、只复用不重写、共享定义修改、同名误绑定、
未授权创建、模型漂移、未知写入与保留清理。真实语义验收以“已建立维修模型，再新增
备件采购”和“已停止 Team 后按反馈改进”两条不同输入检验同一通用路径；验证本轮业务
覆盖、跨切片关系和原有语义保持。具体分母由获准资料及冻结 CQ 确定，不硬编码题数。
验收场景以权威需求 A1—A11 为准。

## 8. 本轮文档检查

需求—决策—设计与 001 依赖一致，检查引用、示例 JSON、结构和 diff；未进行独立设计
审阅、实现或真实建模。不将旧场景 Accepted 或现有绑定函数存在标为通用 029 PASS。
