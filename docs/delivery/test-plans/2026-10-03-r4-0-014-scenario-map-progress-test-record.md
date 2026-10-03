# R4.0-014 场景地图进度与实际产物同步测试记录

## 依据与范围

复用[详细设计 §7](../designs/2026-10-03-r4-0-014-scenario-map-progress-design.md#7-验证计划)及[权威需求 A1—A9](../../requirements/requirements-v4.0.md#r40-014-场景地图进度与实际产物同步)的既定方案。独立测试只读实现与被验证行为输出，只拥有本文档。主 Agent 负责实现和受控角色输入／输出生产。

本轮验证 A1—A8 的结构合同、实际装载、受控角色行为及必要相邻回归；不执行真实 semantic start、平台写入或保留 run 变更。A9 需后续获准真实多视角运行，本次不以受控 Agent 或预写地图替代。

## 前置条件与通过标准

- 环境：`/home/yangxiang/ontology-platform`；Python/uv 测试从 `backend/` 执行，`env -u DEEPSEEK_API_KEY PYTHONPATH=..`。
- 读取根 `AGENTS.md`、需求 R4.0-014、详细设计及当前差异；保护他人改动，产品实现不由测试 Agent 修改。
- 使用实际角色指令/reference/Skill装载的受控输出。独立验证者核对原始输入、候选及输出；不生成或修订被验证地图。
- 各用例必须满足下表预期。机械合同 PASS 仅证明对应结构／传输／保护机制；未执行行为不得判 PASS。缺输入／输出标 BLOCKED，并写解除条件。全部 A1—A8 功能证明齐备才可判本期功能 PASS；A9 单列未验收。

## 复用测试方案

| 用例 | 对应 | 步骤 | 期望 |
| --- | --- | --- | --- |
| T1 结构与实际装载 | A1/A2/A6/A8 | 执行场景地图合同与实际 active Runner 输入测试；核对实际受控角色输入 | 四态、封闭 viewpoint 字段、空 viewpoints 保持合法；普通 note 过期／非全 modeled 不成为新硬门；实际加载更新 reference |
| T2 受控候选交接与修订 | A1—A4/A6 | 读取真实 Modeling/Coordinator 受控输入输出和候选，核对正确交付、无文件口头完成、部分表达＋未知、仅分析及修订失效 | 实际核对当前候选；note 定位且披露范围／未知／下一步；正确使用四态，修订只变受影响范围；不把表达等同 confirmed/applied/PASS |
| T3 消息与权限 | A1/A8 | 核对角色实际输出与 mount/合同测试；读取 CQ 同范围通知受控输出 | 只有 Coordinator 写图；Protocol 不读取私图；隐藏内容隔离；同范围进度通知不重开冻结题池 |
| T4 handoff 原件保护 | A7 | 执行既有 handoff／digest 用例并核对受控行为 | 绑定前完成同步；绑定后仅记差异，原件不改；真实摘要漂移仍拒绝 |
| T5 保存与恢复 | A5—A7 | 执行既有 checkpoint/recovery 与新增紧急保存用例；核对受控恢复输出 | 原图及候选一致恢复；紧急保存不等待同步；当前候选可核对；确定写入不重放，不从 pending 推断未写入 |
| T6 fork 与历史 | A5/A8 | 执行既有 fork／身份／恢复合同并核对受控输出 | 保留中立候选进度，使用新 scope/identity_mapping；旧回执不授权新 apply；缺恢复材料如实报错；源原件不改 |
| T7 后续真实运行 | A9 | 本次不执行；待后续授权真实修订及交接／恢复，由独立验证者读取保留证据 | 可定位成果与下一步；不把地图 modeled 当模型质量 PASS |

## 测试轮次

### Round 1（2026-10-03，进行中）

- 代码版本：`96b90c5e1eea318a776484cae9ff43003a5c6b49`；工作区含本需求 9 个修改文件，测试 Agent 仅新增本文档；未修改产品实现或受控行为输出。
- 范围审阅：当前变更仅角色指令、007 reference、Modeling Skill、宿主 Skill/runbook及两份现有测试；无 Runner/backend/schema/权限接口变化。实现遵循既定四态＋note和唯一写入职责，未引入新硬门。
- 待执行：T1—T6 机械合同；T2/T3/T4/T5/T6 行为证据等待主 Agent 受控输出定位。T7 BLOCKED：本次未授权真实运行，解除条件为后续明确授权与独立保留证据交接。

#### Round 1 执行与结果（23:35 SGT）

实际命令（工作目录 `backend/`）：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_r4007_scenario_map_contract.py \
  ../modeling_team/tests/test_r4007_multiview.py \
  ../modeling_team/tests/test_r30015_resume.py \
  ../modeling_team/tests/test_r30015_acceptance.py \
  ../modeling_team/tests/test_r3012_handoff.py -q
```

实际结果：`98 passed in 10.76s`，exit 0。本测试 Agent 独立执行；没有 LLM/真实 semantic start，恢复／验收测试复用受控平台 stand-in，个别既有用例使用实际 Runner/CLI 进程边界但不调用真实模型提供者。

| 范围 | 本轮状态 | 证据及限制 |
| --- | --- | --- |
| T1 结构／Runner实际装载 | PASS（机械） | 原四态、封闭字段、普通过期 note、active role_sources/Task路径；只证明合同和装载，不证明角色语义行为 |
| T4 digest与handoff边界 | PASS（机械） | `test_progress_note_change_after_handoff_still_rejects_digest_drift`：合法 note 变化仍触发 `collaboration_binding_changed`；既有 handoff排空/unknown write/幂等及不可变测试均通过 |
| T5 紧急保存／恢复／成功写入 | PASS（机械） | 新增 emergency_save用例经 semantic_approved实际保存入口恢复地图和当前候选，源字节不变；`test_m17_completed_plans_map_to_forbidden_resubmission`判 completed_do_not_resubmit并拒绝重复提交；unknown write保持旧核实硬门 |
| T5 验收只读接续 | PASS（机械） | r30015_acceptance完整通过，验证 source-run只读、承接原 handoff/冻结绑定及后续独立验收；production_handoff不能误用生产恢复 |
| T6 fork／历史 | PASS（部分机械），行为待核对 | r4007普通prepare拒绝导入fork授权；本轮未重复运行主 Agent已通过的r30017五例，不把其结果计入独立执行数 |
| T2/T3及T4—T6角色行为 | BLOCKED（待输出交接） | 需要各轮 Modeling/Coordinator输入、消息与地图快照；CQ输出已到但尚未完成整组独立核对 |
| T7 A9 | BLOCKED／本次不执行 | 无真实运行授权；受控输出不能替代 |

结论：机械合同 PASS；整体功能暂为 BLOCKED，待受控行为证据。无本测试 Agent 复现的产品缺陷。主 Agent先前新增fixture误选cq_frozen阶段（34 passed/1 failed）已改用semantic_approved＋现有approvals，此处独立通过；该既知fixture问题不是平台缺陷，不覆盖或撤回其历史结果。

### Round 2（2026-10-03，受控角色行为独立核对，进行中）

- 实现版本仍为上述 HEAD＋本需求工作区修改；生产者主 Agent，验证者 `/root/r4014_independent_test`。读取 `workspaces/r4014-controlled-20261003/approved-test-input.md`、flow-r1/r2、object-r1、`modeling-handoff.md`、`cq-response.md`；验证者没有写这些文件。初始scenario-map仅为输入，不判行为成果。
- CQ 同范围通知：实际受控角色输出逐项保持slice_id/name/scope/owner及原freeze_id/digest，未重出题、开review或terminal，T3/A8受控决策 PASS。没有真实题库文件或Team Transport执行，因此不声称完整CQ生命周期／题库字节不变。
- Modeling正常交接：定位flow-r1与object-r1，并区分部分表达、分析无表达、业务未知、业务范围不适用、无文件口头通知；说明无approval/application/PASS，修订消息保留无关object范围，T2正常表达与定位部分PASS。Round 2消息明确未读flow-r2，故消息不能替代Coordinator实际候选核对。
- 发现 M014-01（Medium，角色行为／prompt-contract）：`modeling-handoff.md` oral段把缺失候选文件写入explicit_unknowns，recovery段把尚无应用证明及无新批准计划也写入explicit_unknowns。复现：使用approved-test-input中的oral及Recovery事实，经已加载Modeling指令生成进度交接。期望：这些是待核对／待办或技术写状态，业务explicit_unknowns只保留真实未决trigger事实；实际：显式业务未知字段混入artifact缺失、应用状态、批准待办。证据为上述message原文，尤其“Actual process expression is unverified because oral-r1.json does not exist”“Whether flow-r2 has any durable application is not established”“No approved new translation or apply plan exists for the fork”。未直接修实现或输出；需检查Coordinator是否过滤，修复／复测由主Agent决定。other/shared-a未confirmed也标未知，业务含义是否真未决未给出充分事实，作为同类风险不单独计缺陷。
- 待核对Coordinator每轮地图、handoff及恢复边界；尚未完整验收A1—A8。

#### Round 2 正式输出与中间输出区别（追加更正）

主 Agent交接说明：上面初读`modeling-handoff.md`时生产者仍在写；正式结束时保留的文件仅初始r1消息，不包含r2/recovery。独立重新读取正式r1：oral缺artifact仍被放入explicit_unknowns，M014-01仍FAIL；other仅proposed没有实际语义歧义，业务未知依据不足。早先r2/recovery观察仅是中间输出风险，不作为正式复现缺陷或已执行修订／恢复案例。先前记录保留，正式结论以此更正为准。

主 Agent已根据该正式缺陷窄修Modeling instructions、Modeling Skill、Coordinator instructions及007 reference，明确缺产物／待批准应用验收／无执行计划属于进度和证据缺口；proposed不自行构成语义未知。未改变Schema／Runtime。独立行为复测尚待新角色正式输出，修复不可仅凭新增文字判FIXED。

#### Round 2 正式Coordinator结果与结论

主 Agent正式交接`coordinator-round1-map.json`及`coordinator-round1-message.md`后独立读取，与r1实际候选逐项比对：flow部分表达为modeled；仅分析为pending；无表达且trigger未知为unknown；明确人工范围排除接口为not_applicable；口头缺文件未虚报已核对；object及shared-a proposed保留；note均指明当前表达／待办责任且未声称applied/PASS。每个slice只登记受测视角，未凑齐七项。源初始图未改。

但Coordinator也将oral缺文件及shared-a仅未confirmed写入地图explicit_unknowns，M014-01在正式地图中复现，整体Round 2为FAIL（Medium，需持久提示修复后行为复测）；非平台写入／Runtime故障。其他正常状态和表达边界部分PASS，修订、恢复与交接后行为仍待执行。

保留证据SHA256：

- `coordinator-round1-map.json`：`13f7fe09dc4ec5a232f7deda36273fcc739e9c3ce9ba9ce44ef7c42241fba921`
- 正式r1 `modeling-handoff.md`：`e5cff5ed4c85bba24d3731f10180747fb8c613f5494c2d59e8d38d7ac1c8e6e6`

### Round 3（2026-10-03，M014-01修复及受控修订／恢复复测，进行中）

- 同一测试方案／记录；修复范围为既有四份权威提示文本，无Schema／Runtime变更。
- 修复后独立命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4007_scenario_map_contract.py -q`；实际`8 passed in 0.11s`，四态及封闭字段PASS。保存／handoff／恢复机械代码及fixture未变，复用Round 1对应证据，不重复扩大测试。
- M014-01状态：待新正式Modeling/Coordinator输出，不凭提示静态文字判FIXED。优先检查业务未知过滤，再核对r2表达失效、无关范围保留、源成功写入不重放和fork身份边界。

#### Round 3 正式Modeling r2复测

正式交接后读取`modeling-round2-handoff.md`并对比实际flow-r2/object-r1：candidate_id=flow-candidate、revision=2、当前仅rule-unknown；消息识别main-flow不再当前表达，process pending而rule必要未知表达modeled，other/object-a保持modeled。不混用source r1成功回执与r2当前内容；明确fork新项目／新identity_mapping、无新批准计划、禁止重放旧写。proposal未确认、无r2应用证明／无新计划均归进度／证据缺口，不再归业务未知。T2修订消息、T6身份边界受控决策PASS，M014-01这些分支FIXED；Modeling oral同输入尚未直接复测。

该正式文件SHA256：`0bbdc9db44907e13561a0698cb2f7dd6c1263142b41c3e13e6631e20918c9cce`。生产者只生成消息，不修改共享图、调用平台或覆写r1消息；这证明受控语义决策，不证明实际Team Transport或完整Team Runner。

#### Round 3 正式Coordinator r2及Modeling同分支结果

正式交接后读取`coordinator-round2-map.json/message.md`：正确核对r2仅rule-unknown存续，将flow/process降为pending、flow/rule modeled，旧main-flow标历史，other/object及shared-a proposed保留，无关analysis/blocked/na/oral进度未重置；保持r1源图。恢复消息明确source-b/source-a/source-receipt只证明源r1成功，不能证明r2应用，不重放源写；fork新身份无新计划不授权apply。T2修订、T5/T6恢复决策部分PASS。

M014-01 STILL FAILING：Coordinator恢复时删除shared-a假未知，却机械保留了oral缺文件假未知，地图explicit_unknowns仍有“oral-r1.json is absent”。复现：以r1过期图＋新r2候选及改后指令恢复工作副本；期望既有误归类证据缺口移回进度note、保留真实trigger未知；实际只修了被r2消息点名的shared-a，未清理oral。Medium，证据为正式r2地图。

M014-02（Medium，handoff顺序／prompt-contract）：正式r2消息`Normal final synchronization`要求“after production work and write draining are actually quiescent ... update ... bind ... before the production terminal”。期望Coordinator更新地图并结束生产后，宿主按既有静默／写排空发布handoff绑定；实际角色把更新放到已静默排空之后，又把绑定安排在production terminal之前，可能形成职责与依赖倒序。未发生实际handoff写入，此缺陷仅是已观察的受控行动说明，不推导运行故障。应窄修Coordinator/对应reference顺序并复测。

修后`modeling-round3-artifact-gap-message.md`正式同oral输入复测：缺文件归evidence/progress gap，true_business_unknowns none，pending且请求实际artifact；analysis和other同样未伪造业务未知。M014-01 Modeling分支FIXED；Coordinator分支未修好。

Round 3总体FAIL（两个Medium行为缺陷）；机械测试PASS，未出现机械回归。保留正式r2输出，不改源证据。

### Round 4（2026-10-03，Coordinator恢复误分类及handoff顺序复测，待执行）

沿同一测试方案优先复测M014-01/M014-02，保留真实未决trigger与中立表达、不重置无关范围。待主Agent窄修权威提示并交接正式角色输出，不以提示文字或脚本预写地图判FIXED。

#### Round 4 执行、证据与结论（23:45 SGT）

主 Agent正式交接Coordinator r3后独立读取[最终地图](../evidence/2026-10-03-r4-0-014/coordinator-round3-map.json)、[最终交接消息](../evidence/2026-10-03-r4-0-014/coordinator-round3-message.md)及[Modeling同oral复测](../evidence/2026-10-03-r4-0-014/modeling-round3-artifact-gap-message.md)，按Round 1既定方案对比真实受控候选和各历史快照：

- M014-01 **FIXED**：Modeling oral明确true_business_unknowns none；Coordinator将旧oral缺文件条目移出explicit_unknowns，保留pending和note里的实际缺口／下一步。最终仅保留flow compensation及blocked rule两项真实未决trigger。shared-a仍proposed，不伪造业务确认。
- M014-02 **FIXED**：正式r3消息明确“Coordinator核对并同步 → production terminal → Host静默／write draining → Host发布handoff并绑定digest”；Coordinator不自发布或绑定，图写入在terminal前结束。紧急保存不等待完美进度；绑定后仅告诉宿主差异，不写源图。
- 必要相邻回归 **PASS**：flow-r2当前仅rule-unknown，process pending/rule modeled；旧main-flow源历史不再充作当前表达；other/object-a当前表达保留；analysis/blocked/na三个无关slice与r1逐字结构一致，shared_terms与r1完全一致。源成功写入不重放，fork新scope/identity_mapping无新apply许可。
- 原件／证据 **PASS**：只读Python逐一校验15份稳定证据与workspace源文件字节相同；四份地图结构校验均无issues；r1地图及r1Modeling SHA256与Round 2原值一致。[manifest](../evidence/2026-10-03-r4-0-014/manifest.json)中的15文件SHA256、五份最终角色/Skill/reference输入SHA256全部与当前文件一致。未声称早期失败输出使用最终提示。
- 无新机械实现变更：Runner、恢复、handoff、Schema未改，沿用Round 1的98项独立机械PASS和Round 3的8项reference结构PASS。主 Agent最终35项直接回归和Skill检查属于开发验证，未计为本Agent独立执行数。

本轮实际验证命令／步骤：只读Python导入现有`validate_scenario_map`对四地图验证，对15证据逐一`read_bytes`比较、SHA256核对manifest，对r1/r3相关切片和shared_terms对比；终态正式消息人工逐项检查。输出为`Stable evidence matches source byte-for-byte: 15`、`Four map snapshots validate without schema changes`、`Unrelated analysis/blocked/na and shared definitions unchanged; only 2 true trigger unknowns remain`、`Manifest: 5 current instruction digests and 15 retained evidence digests match`。exit 0。

| 验收项 | 最终结论 | 证明范围 |
| --- | --- | --- |
| A1 | PASS | 受控真实角色读取实际flow/object候选并定位；口头缺文件保留pending／请求产物，唯一Coordinator写输出地图 |
| A2 | PASS | partial modeled、analysis pending、真实阻塞unknown、业务范围不适用；必要未知已表达和无表达未知分别处理；不把缺资料当不适用 |
| A3 | PASS | 消息及地图不宣称approval/application/独立PASS，shared-a不提升confirmed；表达与业务未知分离 |
| A4 | PASS | r2删除唯一process表达后仅相关进度降级，保留rule与other；历史定位明确，adjustments保留历史 |
| A5 | PASS（受控决策＋既有机械机制） | 从当前候选/过期地图和受控源回执识别下一工作，不重放源成功写；真实恢复mechanism由Round 1stand-in/CLI测试验证 |
| A6 | PASS | 恢复副本清理旧地图误分类并继续，结构允许过期note，不引入全modeled／不可恢复终态门 |
| A7 | PASS（受控决策＋既有机械机制） | 最终角色说明符合terminal/host bind顺序，绑定后只记录差异；实际digest、紧急保存恢复与原件保护由机械用例验证 |
| A8 | PASS（受控决策＋既有机械隔离） | 未凑齐七视角；CQ同范围通知不改变冻结决策；源图/早期输出不改；fork回执不充作新许可；隐藏隔离由原active-input/acceptance测试证明，未向受控角色提供隐藏资料 |
| A9 | BLOCKED／未验收 | 本次未授权真实semantic start，执行数0；需后续获准真实修订及交接／恢复证据，不能以本次受控角色替代 |

总体：**A1—A8本期受控独立功能验证PASS；A9未验收**。本轮无剩余已知缺陷，不建议再发起产品修复或重复机械测试。失败历史及两项Medium缺陷保留在Round 2/3；这是已加载指令的真实受控Agent行为＋复用平台机械合同证明，没有完整Team Runner、真实平台写入、真实checkpoint包／fork或真实模型质量验收结论。
