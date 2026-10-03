# R4.0-014 场景地图进度与实际产物同步设计

## 1. 状态、依据与最小方案

- 权威范围：[R4.0-014](../../requirements/requirements-v4.0.md#r40-014-场景地图进度与实际产物同步)。
  D1—D6 的完整决策及来源以该条目为准。设计轮用户授权需求细化、设计与独立审阅。
- 实际代码核对基线：`5e2c619`；2026-10-03。工作区存在其他任务的代码、测试与宿主
  提示修改；本轮只编写本条文档，不接管 bug 修复，不更改保留 run。
- 需求与设计完成，独立方案审阅 Round 1 PASS（0 Critical／0 High），无待确认关键假设。
  设计审阅时未实施、未运行功能或真实建模验收；审阅记录见 §8，后续实施状态见 §9。
- 继承 [007 设计](2026-10-01-r4-0-007-multiview-collaboration-design.md)的地图结构、共享
  定义与引用重审；继承 009 的独立验收和现有 R3 checkpoint／handoff 恢复合同。

目标是让接续者看清“已有何种表达、依据哪个版本、还缺什么、下一步由谁处理”。
例如流程已有候选、接口版本含义仍未知，地图分别说明其进展；不能全部 pending，也不能
把 modeled 写成所有业务确认、应用和验收均完成。

本期复用四种 viewpoint 状态和 note，通过 Coordinator／Modeling 的现有交接消息与
宿主保存／恢复说明补齐维护纪律。没有新增字段、状态枚举、角色、定时扫描或自动完成判断。

## 2. 现有实现与缺口

| 入口 | 当前事实 | 本期处理 |
| --- | --- | --- |
| [R4 场景地图合同](../../../modeling_team/references/r4-0-007-scenario-map-contract.json) | viewpoint 只有 viewpoint/status/note；四态、note 非空，缺席视角未评估 | 补状态含义、部分进展及更新时机，JSON Schema 不变 |
| [scenario_map.py](../../../modeling_team/scenario_map.py) | `_validate_viewpoints` 只查字段／枚举／重复；`_validate_candidate_refs` 可核对结构化候选引用及当前 revision | 复用结构检查，note 内的语义引用由角色核对，不添状态评分器或正则硬门 |
| [Coordinator 指令](../../../modeling_team/agent-packages/coordinator/instructions.md) | 已唯一负责地图、共享身份及重审，但缺明确的持续进度更新动作 | 增加候选交接、修订、交接前和恢复后的核对步骤 |
| [Modeling 指令](../../../modeling_team/agent-packages/modeling/instructions.md)与[建模 Skill](../../../modeling_team/skills/ontology-modeling/SKILL.md) | 已要求给 Coordinator 提供 coverage、由后者写地图 | 明确交接消息中的定位／已完成范围／未知／下一步，避免“完成了”空泛消息 |
| [codex.py](../../../modeling_team/runtimes/codex.py) | `_coordinator_scenario_map_bind` 只有 Coordinator 可写 run 根地图；`_staged_decision_binds` 给 Coordinator 完整 stage3 只读树 | 实际候选可以直接核对；Modeling／Protocol 不能代写地图，不改变 mount |
| [runner.py](../../../modeling_team/runner.py) | `_cq_publish_production_handoff` 保存地图路径和 digest；checkpoint 收集地图、候选、计划和回执 | 更新安排在绑定前；复用保存，不新增检查点字段 |
| [__main__.py](../../../modeling_team/__main__.py) | `_cq_collaboration_context` 检查地图 digest，改变则拒绝；仅向 Judge 投影获准可见资源的协同状态 | 验收期间保持原图；不能把“修备注”当作可忽略摘要漂移 |
| [checkpoint_recovery.py](../../../modeling_team/checkpoint_recovery.py)及 Runner | 原产物恢复、角色接续 packet、新 fork 的 scope／identity_mapping 已存在 | 在接续角色指令中核对地图与实际内容，不重写恢复引擎 |

这些是代码阅读结论，不是本轮测试结果。既有 checkpoint 捕获 bug 的修复状态由对应交付
记录负责；本条验证使用当前真实恢复入口，不把旧包不完整问题隐藏成“进度未更新”。

## 3. 状态与内容表达

### 3.1 viewpoint 状态

状态按权威需求定义：有可定位当前表达为 modeled，可为部分范围；无表达但已有工作计划
为 pending；无可确认表达且依赖业务未知／冲突为 unknown；有当前业务范围依据证明不适用
为 not_applicable。未登记仍未评估。modeled 是“存在表达”的工作事实，不是质量或完成认证。

混合情况用一个原有状态加清楚说明，不新增 partial：

- 已表达范围 A，范围 B 未开始／未知：modeled，note 同时列 A 与 B。
- 已分析流程但没有候选表达：pending；若卡在未决业务事实，unknown。
- 候选已经正确保留必要未知：modeled，同时列该未知及后续需要；不能说业务事实已确认。
- 当前修订删除了原有唯一表达：重新按 pending／unknown 判断，note 指明旧版本是历史。
  若仍有未失效的表达则保持 modeled 并收窄已完成范围；不是无条件单调推进。

`slices[].status` 仍是非空文字，可写“建模中，流程已有表达，接口映射待确认”。不强制
套用 viewpoint 枚举，不从七项状态计算百分比，也不把同名的 shared_terms.status 混用。

### 3.2 note 及现有相关记录

每个受影响条目的 note 应能回答：当前已分析／已表达什么；依据哪个现有候选版本和
关键 item；还缺什么或未知什么；下一步及其责任／输入。全部完成或无未知可明确写无，
不强制固定文案或逐个 item 全量罗列。相同定位可合并覆盖一组内容，必须足以核对范围。

片段示意（不是完整地图，也不提供真实业务事实）：

```json
{
  "viewpoint": "process",
  "status": "modeled",
  "note": "已表达：主流程与异常回退，见 candidate-flow r3 / flow-main、flow-fallback；未完成：补偿路径；未知：补偿触发条件待业务负责人确认。下一步：Modeling 根据确认补齐候选，再由 Coordinator 更新本条。候选未应用。"
}
```

该对象没有增加 `candidate_refs` 字段。共享定义的结构化 candidate_refs 仍在原 shared_terms
中维护；不得把其结构直接复制为 viewpoint 新字段。当前候选按已发布完整 revision 核对，
旧版只作为历史说明，不能用新文件名套旧内容。结构引用更新时遵守现有 stale revision 检查。

真实未知用已有 explicit_unknowns 的 topic/needed_from/status 说明，必要内容同样保留在
候选 unknowns／conflicting_meanings 中。未开始但没有业务事实疑问的待办只写进度，不
伪造成业务未知。解决未知后依实际确认更新已有条目，不静默从地图删去未解决问题。

adjustments 仅在实质进度变化时追加一条简洁 change／approved_by_coordinator；可合并
同次多个视角，记录原因和当前产物定位，不按每个工具调用记流水账。共享含义发生变化时
沿 007 填 review 并重审引用，不能借“只是进度更新”绕过。

## 4. 消息与更新流程

### 4.1 正常候选交接／修订

1. Modeling 发布现有完整不可变候选，通过既有 Team Transport 消息告知 Coordinator：
   slice_id、相关 viewpoint、candidate_id/revision/item_id 或对应文件位置、实际已表达
   范围、未知／待办、下一步。修订时说明旧版哪些内容仍有效或被替代。不创建新 RPC／Schema。
2. Coordinator 从只读 stage3 候选挂载核对实际内容；message 只是定位与说明，不能替代
   产物。文件不可用、修订不匹配或无法确认含义时，向 Modeling 反馈具体缺口并保留
   “待核对”说明，不按对方口头完成声明提升状态。其他独立工作可继续。
3. Coordinator 在 `/agent/work/scenario-map/scenario-map.json` 中只更新受影响切片／视角、
   相应未知及 adjustment。语义不变的修订仅换当前定位并说明，不清空无关内容。共享定义
   变化按 007 另核对直接和已知间接影响，不为进度更新扩大到无界扫描。
4. 复用现有结构校验反馈；状态是否符合实际内容由 Coordinator 判断并交后续独立验证。
   不为每条 note 新加后台验证、哈希字段或审批。结构引用错误仍须修正后再提交受影响操作。
5. 若需要说明已应用状态，Coordinator 通过 Protocol 的已有消息取得确定结果摘要；
   Protocol 不读取私有地图。实际权限与资源、回执核对仍由原职责处理，地图不是写入许可。

消息可搭载现有候选交付／修订通知，不要求额外确认回合或固定 Agent 数。Coordinator
未及时更新属于可修正协作遗漏，返回切片／视角／候选定位即可；不终止安全 run。

### 4.2 正常生产交接与计划保存

Coordinator 在其生产结束声明／terminal 之前核对当前交付候选与地图，Modeling 的最终
消息给出剩余未知与待办，Protocol 的结果保持写入事实边界。宿主在现有交接检查中核对
地图是否能说明这些成果与缺口，不另建“必须全 modeled”门。

正常顺序：最终候选／现有写入结果明确 → Coordinator 更新并结束地图写入 →
原有生产静默及写入排空 → 宿主既有 handoff 发布并绑定地图 digest → 独立只读验收。
Coordinator 在结束工作前完成同步，避免等其 terminal 后才要求未授权重启角色修备注。

计划 checkpoint 保存时先尽量完成已到达的更新；紧急中断、额度或期限到达时保存当时
实际地图和产物，允许地图尚未同步。已有 checkpoint manifest／stage_facts 继续如实
记录，并在宿主保存说明中标待核对部分；不能为更新地图拖延必须停止的生产任务。

### 4.3 handoff 后发现过期

handoff 已绑定地图后，不在原 run 中覆盖地图，也不改 handoff digest 或 checkpoint。
在宿主用户交付记录中写明“地图此项过期；实际候选定位；待后续恢复时同步”；这些说明
不进入本批 Judge 的业务证据，不自行改写旧报告。独立验收仍使用其原获准证据和真实缺口。

本需求不因普通 note 过期要求重启验收／重建模型；若有人确实改坏已绑定地图，按既有
`collaboration_binding_changed` 保留真实故障，不能绕过摘要校验。若要重新进入生产和
再次验收，按既有获准恢复／新 attempt 流程进行，额度和授权不由本条增加。

## 5. 恢复时的事实核对

恢复顺序沿原机制：验证 checkpoint／scope／身份映射和写入状态 → 读取恢复候选及地图 →
确定已有效表达范围与真正待办 → Coordinator 更新允许写入的恢复工作副本 → 执行下一步。

- 地图 pending 不说明平台尚未写入；读取恢复链的 Batch／Attempt／回执和既有 adjudication
  结果，确定成功不重复 apply，不确定写入先沿原机制核实。不能用“进度落后”触发重放。
- 当前候选与 note 版本不一致时，先查实际有效候选、批准和恢复说明；新版提案不自动继承
  旧批准，旧批准也不证明新版完成。只重核受影响范围；共享 review pending/deferred 保留。
- 已绑定 handoff 的只读恢复阶段继续保留源地图；如只需继续独立验收，不因本需求改地图。
  真正恢复生产后，在该阶段允许修改的新工作副本更新，不覆写源 checkpoint 或只读原件。
- fork 保留中立 candidate_id／item_id 及已有表达进度；平台执行依据新的 fork_scope 和
  identity_mapping，原 Project 回执只保留源语义。源 note 中旧平台标识只能明确标历史，
  不能当新目标的已批准计划。新的翻译／应用验证继续按原 fork 合同，不新增进度恢复 API。
- 包缺少候选／恢复历史是既有恢复缺陷，明确报告实际缺失，不能从 note 重造批准或候选。

`_cq_check_scenario_map_slices` 现有 fingerprint 含整个 map_digest，备注更新可能再次发送
`cq-slices-approved`，但这不是新用户批准或重新冻结。CQ 指令须明确相同 slice_id/name/scope/
owner 的进度通知只作状态信息，不重新出题、不修改冻结池；真正切片范围变更走原审核流程。
不为减少通知顺带改 Runner 去重算法，验证只读进度更新不会制造新业务决策。

## 6. 实施范围

| 文件 | 计划增量 |
| --- | --- |
| `modeling_team/references/r4-0-007-scenario-map-contract.json` | 四态语义、note 示例、触发时机与 handoff 边界；保持字段／枚举／版本 |
| `modeling_team/agent-packages/coordinator/instructions.md` | 实际内容核对、唯一作者、部分范围、结束生产前同步及恢复核对 |
| `modeling_team/agent-packages/modeling/instructions.md` | 在候选交付／修订消息中报告实际覆盖、定位与剩余工作，不写地图 |
| `modeling_team/skills/ontology-modeling/SKILL.md` | 补充维护进度所需的语义方法与交接信息，保持角色边界 |
| `modeling_team/agent-packages/competency-question/instructions.md` | 同范围重复 slice 通知不重开冻结题池，进度不是新业务批准 |
| `skills/modeling-dev-loop/SKILL.md`、`references/team-runbook.md` | 正常交接／保存／恢复检查与交接后过期说明，衔接 013 已设计的汇总边界 |
| 现有场景地图、角色合同、checkpoint／handoff 测试 | 有界补充状态说明、结构不变、原件保护与实际消息场景的验证 |

活动 R4 Task 已为 Coordinator／Modeling／Protocol 挂载 007 reference，正常情况下无需
新增 role_sources 或 014 专用 Task；实施时验证实际组装输入包含更新内容。旧 R3 地图
依原合同，无批量升级。Protocol 现有写入职责足够，本条不新增平台接口。

Runner、scenario_map 校验器、checkpoint/recovery 引擎及后端本期只复用，不计划改代码。
不得为方便 note 展示引入自动状态计算、重复业务确认或 apply 状态。若实施中证实入口缺失，
按当前证据修最窄缺口并更新设计，不把它当提前建设新框架的理由。

## 7. 验证计划

| 层级／场景 | 验证要点 | 验收对应 |
| --- | --- | --- |
| 结构与实际装载 | 新说明和示例在原四态／封闭字段下合法；仍允许空 viewpoints；校验器不会因 note 过期、非全 modeled 拒绝；角色实际挂载更新 reference | A1、A2、A6、A8 |
| 受控协作行为 | 给实际 Coordinator／Modeling 受控候选和消息，包含正确交付、口头完成无文件、部分表达＋未知、只有分析、修订使旧表达失效；独立验证者检查地图与原内容 | A1—A4、A6 |
| 消息与权限 | 唯一 Coordinator 写共享地图，其他角色交内容；Protocol 不被要求读取私有目录；CQ 同范围进度通知不重新出题；隐藏资料不进入地图 | A1、A8 |
| handoff | 交接前更新被 digest 绑定；交接后仅记录过期说明，原文件不变；真正修改后既有 digest 检查仍拒绝，不能借进度豁免 | A7 |
| 保存／恢复 | 原地图与候选保存恢复一致；过期 note 恢复后核对当前候选；明确成功写入不重放，未知写入不从地图推断；紧急保存不加等待门 | A5—A7 |
| fork／历史 | 中立表达进度可保留，平台身份引用新映射；旧回执不能授权新 apply；原包和原交接不改写；缺少恢复产物如实报错 | A5、A8 |
| 后续真实运行 | 在获准真实候选交接、修订、handoff 或恢复中取得相应地图前后内容及产物；独立检查接续者能确定下一步 | A9 |

复用 `test_r4007_scenario_map_contract.py`、`test_r4007_multiview.py` 中结构、候选引用、
save/restore 与 collaboration digest 案例，及实际 checkpoint／CQ 生命周期测试。行为验证
需要真实角色输出或可审阅的实际协作记录；脚本预先写好地图只证明文件／传输，不证明角色
遵守语义。A9 的真实建模运行需后续另行授权，不能以受控功能案例替代。

设计轮只做文档链接／结构／编号／diff 检查。实施后对改动 Skill 使用适用校验，并运行相关
Team 合同与功能测试；没有 backend/frontend 改动不启动其套件或重启服务。临时测试文件
按全局规则清理，正式交付与审阅证据保留。

## 8. 独立审阅记录

| 轮次 | 结论 | 发现与处理 |
| --- | --- | --- |
| Round 1 | PASS，0 Critical／0 High | 独立 plan_reviewer 核对四态＋note、Coordinator 唯一写图与候选只读挂载、handoff digest 前后边界、CQ 同范围通知、checkpoint／fork 不重复写入及分层验证；无阻断，无待确认关键假设 |

审阅 Agent：`/root/r4014_plan_review`，2026-10-03；实际核对基线包含其他任务提交
`152de58` 的既有修改。审阅只读，未改文件、运行测试或启动服务。PASS 后仅回填状态与记录。

文档链接／锚点、F1—F5／D1—D6／A1—A9 编号、围栏、JSON 示例及 diff 检查已通过；
相邻 013／015 正文保持不变。独立审阅只证明方案，未实施、未执行功能或真实语义验收。

## 9. 后续实施与独立功能验证

用户后续明确授权按设计开发与测试，已按 §6 完成角色、reference、Skill及宿主说明增量，
并在两份既有场景地图测试中补充四态封闭结构、普通过期、合法 note 摘要漂移、实际语义
阶段保存／恢复候选与源图保护。未修改 Runner／平台／恢复引擎或保留 run。

开发回归 160 passed，最后提示修订后直接相关 35 passed；独立机械回归 98 passed，修后
结构验证 8 passed。实际受控 Modeling／Coordinator／CQ 子 Agent 加载当前指令生成消息
与地图，独立检查者对照实际输入，发现并窄修“进度／证据缺口误归业务未知”和“角色结束／
宿主绑定顺序混淆”两项提示缺陷；最终 Round 4 A1—A8 受控独立功能 PASS，首轮和第二轮
失败输出保留。此验证不声称完整 Team Runtime或真实平台写入／恢复 E2E。

[交付记录](../records/2026-10-03-r4-0-014-scenario-map-progress-delivery-record.md)与
[独立测试记录](../test-plans/2026-10-03-r4-0-014-scenario-map-progress-test-record.md)提供分层
结果和稳定证据定位。A9 后续真实多视角运行未授权、未执行，需求整体 PARTIAL。
