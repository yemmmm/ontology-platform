# 修后 Demo 专职多 Agent 建模测试

日期：2026-11-04。目标：验证 R5.0-012 修后真实专职协作和完整 Demo 建模质量。

**最新结论：追加3 CNY后总授权6 CNY已耗尽，累计估算6.03286852 CNY，run已停稳且无在途。实际apply完成，143项资源绑定、Ontology revision 2；专职角色采用和CQ治理读回已观察，原属主专用自查被冗余self-review路由拒绝，正式独立验收0/36项执行。整体PARTIAL，L0未闭环，L1/L2未验证，不能保证多Agent建模质量。原模型、会话和失败证据保留；无额外付费调用授权。下文首批3元统计保留为历史截止，最新接续证据见文末。**

来源：[R5.0-012/011](../requirements/requirements-v5.0.md)、[修复记录](../delivery/records/2026-11-04-role-team-live-contract-fixes.md)、[v5 runbook](../../skills/modeling-dev-loop/references/v5-runbook.md)。

配置：scripts/modeling、role-team/v1；所有托管生产、过程评价与独立评价均 glm-direct/glm-5.3-flash/high；独立 3 CNY 金额预算。一轮新建模，不沿用旧项目、候选或 PASS。复用上一轮冻结 Demo 原文、API、Schema 和公开 CQ；36 项原独立标准隔离保留，生产不可见。evaluation.model_read_scope=whole_model。

输入：`workspaces/v5-runs/demo-role-high-20261104-inputs`；运行：`workspaces/v5-runs/demo-role-high-20261104-start1`；代码：`365f6db`。其他工作树改动保留。

**首批3元暂停时：PARTIAL，金额预算暂停已停稳。三个专职角色、公开 CQ 和 143 项候选整合已实际采用；停在 apply 前，实际模型 revision 0。L0 未闭环，正式 L1 0/36 项执行、质量未验证，L2 未执行。** 公开 Demo 不构成客户业务盲测或普遍质量保证。

## 首次真实启动

Modeler 原生 turn/started：2026-11-04T05:37:24.363707Z（来源分析用途，实际读取及业务命题仍另核对）；Coordinator 独立执行同时在途。prepare 2026-11-04T05:37:07Z，代码 HEAD 365f6db。预算在调用前成功创建，所有四类模型绑定均 high。授权时间以首次工具前保守界05:33Z记录，精确消息到达未知，不能声称精确启动延迟。

## 范围接纳与过程评价启动

Coordinator 首轮已提交精确范围成果，root 进入 waiting_children，work-tree revision 2；既有 cq-public 分派与身份已被接受，Modeler 分配阶段为 propose（首个 intake 原生回合仍在途，等待自然结束后消费新范围）。CQ 在独立上下文实际启动。当前一名 Modeler 承担两个紧密业务切片，不强造第二名；因此本轮尚无多 Modeler/递归父级协作证据。

切片方案评价绑定 `3299acee807b107cc468f5c60437db14efa09d036943df3e3c201627d4d33fd6` 已 queued 并实际执行，来源仅公开包，评价结果不回灌生产。

## 过程观察（尚未完成）

首个 Modeler 来源分析已正式接纳并交接，随后按已安装 generation 1 的 scope 进入 propose，沿用本轮初建目标。程序 round 数不是业务建模轮次数。Coordinator 的范围包已接纳，CQ 专职 public-cq-set 已接纳；前轮范围未安装、cq-public 身份误拒、公开 seed 输入错误在此路径均未复现。完整材料消费的整合验证仍待实际交接，不提前宣称该修复已完整验证。

切片过程评价完成，四维各 4 分，但 scope_allocation 与 whole_rules 标 low 缺口，因此 satisfaction=gaps。评价者认为计划枚举未显式列出 Bearer 认证、提示空格保真、本地回复格式和权限边界；同一计划仍明确要求完整来源读取。它是方案诊断，不能直接推导实际模型遗漏；高分与低优先级缺口的并存保留原报告，不能平均成通过。

公开 CQ 专职复核 Q1–Q9，并新增 R1–R4 draft 规则簇；Q3/Q4 状态编码映射待核对，Q7 时间格式/时区、Q8 拒绝/回放事件来源、Q9 调价历史/操作者依据不足明确保留。该支撑映射为原文层，不是模型层证明。公开 CQ 过程评价绑定 `e4481faf6b07a746c5158f0a693b21ac8cd298e0f50509ebae851a19715e4aa3` 已启动。正式独立 36 项验收尚未启动。

### CQ 过程评价结果

已完成，satisfaction=gaps。goal_coverage=3/low；clarity、conditions_and_cross_unit_questions、source_fidelity 均4/none。缺口为模型标识登记后不变、提示原文含空格保留、本地回复格式未明确进入问句覆盖，也未记入该 CQ 成果 coverage_gaps。未核对部分：部分 Q5–Q9 注记与 API 中部路径因工具回显截断未逐条核对；不能把报告分数当作完整读取/全模型证明。原件 `inputs/process-cq-result.json`。尚无实际模型，整合评分和正式独立 L1 未启动。

## 首个正式阻塞：候选输出缺失

Modeler `modeler--role-00002` 原生回合 status=completed/error=null，但 result.json.final_response 仅含进度文字，最后声称将交付完整建议，没有实际 JSON 候选。程序返回 `role_result_invalid / result_json_missing_or_ambiguous`，标 platform-contract/recoverable，并自动将原责任单元接续至 `modeler--role-00003`。已保留的命题、决策/覆盖记录与卡片没有被宿主替写；没有实际模型 application。卡片中的“223项已定稿”不作为候选已提交证据。此为输出合同采用失败，不能据此推导模型语义质量差；是否涉及模型/供应商截断机制尚未确定，保留第一层错误而不猜原因。技术格式纠错仍属于本轮初建，不另授权实质修模。

### 输出纠错已走通

`modeler--role-00003` 最终交付被接纳，原单元进入 proposal_ready，Coordinator 已开始 `role-00001` 整合回合；不再只是卡片自述。未修改平台代码、未由 Host 编写业务候选，沿原 run/预算继续。当前计价约1.5032 CNY。旧失败原件保留；尚未发生实际应用，独立质量未验收。

## 整合首次提交的可恢复拒绝

Coordinator `role-00001` 返回 integration-plan/v1，但 `source_refs=[]`，实际被 `role_artifact_or_sources_missing` 拒绝；原始候选和 CQ 均 proposal_ready，active={}，无 application。原件表明角色间材料消费校验已通过，此处不是前轮 JSON 参数比较的误拒。原整合计划另有可直接核对的技术合同错误：把无候选的 CQ 放进 contributions，check_units 混入 CQ/root，ontology_targets 用 slice ID 代替变更 ID。Host 通过原 input 通道仅解释这些字段合同、要求保留原作者业务正文和已拒计划做局部纠错，再 resume 原 run，未提供业务答案、未改候选或代码。计价1.84255024 CNY，余额1.15744976。

T0复核：当前非空且实际来源引用保护来源可追溯性；拒绝可恢复且无不确定写入，不是永久 run 硬死；删除会允许不可追溯的整合提案；Agent 可按现有读取/反馈自行修正；原子 apply 只保护写入完整性，不能代替来源依据。因此本次保留来源合同，走准确反馈与原计划局部修正，不扩展平台机制。额外字段指导直接来自当前 integration-plan 合同，不取自私有评价。

### 单字符技术身份错误

`role-00002` 修正计划已通过来源/贡献/消费/检查单元约束，但 compose 阶段因 `integration_placement_unknown` 拒绝；平台未写入，原进程自动进入 `role-00003`。对照当前 qualified_id 函数与原 result_ref/selected_change_ids，143 个放置 key 中142个相符、1个少一字符：错误 `c-e0d19e2704f4b1252fda516eed3d5d7`，程序值 `c-e0d19e2704f4b1252fda516eedd3d5d7`。Host 仅将这份确切标识差异发回原通道，未改语义或候选。该守卫保护真实变更/放置身份，不能删除以换通过；错误反馈本身未列出 offending key，是定位反馈可改进点。预算约2.1875 CNY，余额0.8125；没有追加。

`role-00003` 再次触发同一 placement 错误，原件对照仍是同一个31字符 key，并非新增143处不一致。精确 Host 纠错消息在该原生回合忙碌时 queued，到后继 `role-00004` 才 delivered；发送不等于本回合已读/消费。上一份字段合同指导已由 `role-00002` consumed。当前保留消息状态与执行绑定，不能把这次自然边界等待误判为消息丢失，也不能把第三版卡片的“修正”自述当作程序通过。预算约2.5984 CNY，余额0.4016，仍未写入。

### 精确字段修正后仍需重读原贡献

`role-00004` 已确切修正错字，离线使用原 qualified_id 函数核对143个放置key全匹配（unknown/missing均空）；精确Host标识反馈列入 consumed_ids。但该回合只消费了保留的整合计划，未将本回合原 Modeler 材料读取列入 consumed_refs，触发 `contribution_not_consumed`（准确携带 owner_work_id 与 material_ref）。程序再开 `role-00005` 补读原贡献，未发生写入。当前约2.8530 CNY/余额0.1470。局部字段纠错仍触发完整原贡献/来源的当回合读取义务，未变材料复用与校验成本存在张力；本轮保留当前冻结合同，没有为换通过而放宽读取校验或改写候选。该条是实际成本/合同采用观察，是否修改平台消费复用需后续独立评审，不冒称已经定位为实现bug。

## 暂停时的实际结果与验收边界

最后 `role-00005` 完成原贡献补读，整合计划已被程序接纳，组合对象保存为 `run:demo-role-high-20261104-start1:role-result:0:5:composition`（digest `751c25bf58e75f3585cae8b77db5a9700dbd22d7971aa3b0b4c873af6a7bcd5d`）。143 个候选项、143 个 create 变更，286 个 item/change 追踪条目均保留原 `modeler` 作者；这是工作空间组合成果，不是已应用模型。根状态 `paused / activity=apply`；`control.mode=running` 是用户控制字段，预算另以 `budget_open=false` 拦住准入，`status=settled / active={}` 表明已无在途活动。

暂停快照 `ca8624b1929443539897f17cd9beb7e5`：Project `d33f9326-c34c-438d-98c5-2659bbfd9657`，Ontology `774705e8-ecf4-40c5-957d-e44c94f72377`，revision=0；resource_refs/resource_bindings 均空，role_application 对象为0，model_read_error=null。snapshot.object_count=76 是工作空间对象数，不是模型资源数。平台数据快照的临时读取凭据有 revoked=true 回执。

| 验证面 | 本轮实际证据 | 结论 |
| --- | --- | --- |
| R5.0-012 F1/F2/F12 | 默认 role-team/v1，Coordinator/CQ/Modeler 独立身份、原生上下文与成果；全部12次托管执行原生绑定均 glm-5.3-flash/high | 真实采用已观察 |
| F3/F4/F5 | 范围正式安装；原九题复核与R1–R4 draft；Modeler正式候选与Coordinator完整材料消费 | 局部闭环；不把draft标准当业务事实 |
| F6/F7 | 143项组合与原作者追踪已保留，引用与放置检查最终通过 | 组合已观察；编译/原子apply/实际回执尚未执行 |
| F8/F10/A11 | 格式/来源/标识/消费错误均可重入，原产物保留；两份Host技术指导分别真实消费 | 恢复已观察但代价高，非完全自主交付；通用错误缺精确坏key定位 |
| F9/A15 | 未写入，因此原作者治理读回、CQ刷新、根整体自查、36项正式独立评价均未执行 | L0未闭环、L1未验证；不能据此判模型质量好坏 |
| F11 | 同一3 CNY预算计量，余额关闭后不再开新回合，最后在途自然结束 | 本次金额暂停已停稳；不等于3元严格硬费用上限 |
| A3/A16 | 一名Modeler承担两关联业务切片；无多Modeler/递归父级实际组合、无同条件第二轮 | 复杂协作与L2未验证 |

过程评价覆盖三点中的两点：切片4/4/4/4，但两维priority=low，satisfaction=gaps；CQ为3/4/4/4，覆盖维度low，satisfaction=gaps。两者均为固定公开成果的只读诊断，不回灌生产、不因低分重跑。CQ另保留部分回显截断未逐条核对。整合未观察（没有实际模型修订），正式独立报告引用为空。汇总的 evaluation_complete=true 只表示已提交的两份诊断已结束，不表示三个阶段全部完成或质量通过。

任务级fresh run=1；业务初建=1、已应用模型修模=0。实际Modeler原生执行3次、Coordinator6次、CQ1次、过程评价2次；semantic-starts目录有1份首次source_intake记录。原生回合数、阶段round字段、任务启动数和业务修模轮次不互相替代。

## 截至暂停的时间、token与金额

统计记录时点 `2026-11-04T08:12:50.801141+00:00`。可核对原生执行窗 `2026-11-04T05:37:20.646000+00:00` 至 `2026-11-04T08:07:59.385000+00:00`，9038.739秒（2小时30分38.739秒）；准备落盘 `2026-11-04T05:37:07.578491+00:00` 至本次记录 9343.223秒。精确用户消息收取时间未知，不能把保守授权时间界当精确总任务起点。

| 角色/用途 | 原生执行数 | 输入token（含缓存） | 输出token | 原生区间并集秒 | 冻结价表估算CNY |
| --- | ---: | ---: | ---: | ---: | ---: |
| Coordinator | 6 | 3,003,337 | 297,341 | 5505.112 | 1.84810196 |
| Modeler | 3 | 1,841,716 | 181,549 | 3727.383 | 1.04463136 |
| 公开 CQ | 1 | 275,995 | 27,766 | 537.781 | 0.17462636 |
| 过程评价 | 2 | 101,887 | 33,569 | 732.758 | 0.17958956 |

输入合计 **5,222,935**，其中缓存输入 **4,221,312**；输出 **540,225**；输入加输出 **5,763,160 token**。按12个不同原生线程末次累计counter统计，未累加中间累计样本，失败/纠错均纳入。覆盖12/12 known，unknown=0、provisional=0、inflight=0、pending_settlement=0。

生产原生区间并集 8868.551秒；过程评价区间并集 732.758秒，与生产重叠，不能相加为总墙钟。区间包含推理、工具和供应商等待，不等于纯语义有效劳动。Host准备、技术指导与记录整理的有效劳动及外部Host token未完整采集，保持unknown、单列且不扣任务金额；全任务计量仍PARTIAL。

授权3 CNY，已知原生用量按冻结价表估算 **3.24694924 CNY**，余额 **-0.24694924 CNY**；最后已准入回合自然结束形成尾差，没有追加预算或开启后继回合。原生token三桶重算与账本精确一致；这是本地价表估算，不是供应商最终账单。tail_bound仍有control_delay缺少limit导致的unknown，不能把它称为已知零上界；它与当前已知12/12计量、无在途/无待结算是不同字段。

## 资源保留、下一步与证据

未执行stop或cleanup，保留同一run、项目/本体、角色成果、组合对象、原预算及必要运行绑定，以便获新金额授权后先核对revision 0再从apply接续；不是重新建模/重置额度。最后源CLI已退出，所有在途原生调用均结束。本次交接后没有另行安排后台监控，预算关闭使后继调用不能准入；保留原角色/工作空间不代表仍在自动推进。快照临时读取key已撤销；run级后续接续能力没有被此快照操作清理，未宣称所有run级密钥已撤销。

剩余实际步骤：编译/原子应用→原Modeler治理读回→CQ支撑刷新→Coordinator整体检查→实际模型整合诊断→独立冻结36项whole_model评价。新金额授权前不执行这些后继调用。若用户决定结束而不接续，再按原run归属stop/cleanup；不先删除空scope再声称能原地resume。

关键原件位于 `workspaces/v5-runs/demo-role-high-20261104-inputs/`：`OUTCOME-AS-OF-PAUSE.json`、`status-final.json`、`budget-final.json`、`observed-usage-summary.json`、`snapshot-budget-paused.json`、`process-summary-paused.json`、`process-slicing-result.json`、`process-cq-result.json`、两份技术指导及投递回执、start/resume原日志。run目录保留executions、semantic-starts、快照和平台数据。

本轮未修改平台代码、模型Profile、获准源材料或独立题集；最终manifest/题集摘要和12份原生模型/effort绑定复核通过。只新增本记录并同步归属需求状态，执行本地链接/格式与证据一致性检查；无需前后端套件或服务重启。这些检查不构成真实模型质量验收。

## 用户追加3元后原run接续

用户回复“同意增加额度”，对应上一条明确追加3 CNY请求。Host按 `user-20261104-demo-role-high-add-3-01` 向原账本追加3元，总授权6 CNY；此前3.24694924元用量保留，续跑前余额2.75305076元。恢复前实际平台快照确认同一Project/Ontology仍revision 0、资源引用为空，原run paused/apply且无在途；未删除scope、未重置预算、未新建任务或替换Profile。沿已保存143项组合从apply恢复，后续状态另记；上一节暂停原件与统计不覆盖。

### 续跑首次application：字段形状拒绝，未写入

`apply-00006` 保存 application_reference，status=not_written；候选校验返回 `unified_schema_mismatch / candidate item fields drift from the contract`，所有定位仅/candidate，未给item_id。程序把原Modeler generation重开到2（modeler--role-00006），Coordinator等待，不新建run。Host按systematic-debugging先追原始载荷和权威合同：143项都缺中立item包装字段，13项仅缺relation_endpoints，60项两者均缺，70项仅缺shared_scope；没有额外字段。与原Modeler原生JSON逐项比较，同样缺失，排除Coordinator组合丢字段。未改候选或代码，只将精确字段存在性差异交回原Modeler，要求保留原业务正文、真实端点/共享定义及未知。此技术反馈在忙碌回合中投递仍以实际delivery/consumption为准。

T0：实际关系端点/共享语义不能由Host猜造；本轮拒绝已明确not_written且可重入，不是永久run死亡。缺省空字段的强制存在性与v5外层结果schema宽松存在合同张力，但当前冻结技术合同明确八字段闭集；先沿准确反馈允许原作者补正，不以删除校验放行未经编译/原子应用验证的载荷，也不把此格式拒绝归为模型语义质量差。是否将无业务含义的空字段改为边界默认值，应另做窄合同一致性修复；本轮尚未修改生产代码。

Host另给下一整合回合一条中立技术澄清：当前恰有一个已授权Ontology，worker现有逻辑支持ontology_targets={}自动落到该唯一目标，等价于已选放置、不改变拓扑；避免新贡献版本后重复抄143个新hash。源码已核对，Coordinator在无ready子级时会在LLM调用前保持waiting_children，因此此消息不为等子级额外开空推理回合。未修改代码或Candidate业务字段；是否采用及实际消费仍看后继原生回执。

Host复用现有纯静态编译器做一次内存副本假设检验：只对缺失的两个中立包装字段setdefault(null)，并镜像Host实际candidate_ref技术注入，143项候选形状错误归零，静态编译得到2批计划、无下游静态编译错误；原candidate.json SHA/字节保持未变，没有执行平台write或生成替代Modeler候选。首份本地诊断曾漏模拟Host注入candidate_ref而产生假性candidate_ref_required，已在诊断原件标明并修正，未把这些假错误送给Team。此复核只支持包装字段是当前静态阻塞层，不证明API apply、实际治理读回或业务语义质量。原件neutral-wrapper-static-diagnostic.json。

`modeler--role-00006` 原生结果实际143项/143变更（45 entity、20 property、4 table_mapping、4 join_mapping、70 relation），原条目ID无丢失；卡片135是数错，不能当实际范围减少。原回执所有relation_endpoints字段已补齐，但仍131项缺shared_scope，12项包装字段齐全。Host的精准字段反馈在忙碌回合后送入 `modeler--role-00008`，原Modeler继续技术补正；没有用Host静态副本替代其正式候选，也没有将“不丢ID”当作全部业务正文/语义已经验收。

`modeler--role-00008` 实际正式结果已接纳，143项/143变更、原item_id无丢失；必需八字段全部齐全，13个原非空shared_scope标签与原始正式版本一致（含先前重写丢失的一处已恢复）。复用现有静态compiler对实际新载荷复核：0 candidate schema错误、0静态编译错误、2批计划；无需插入假设空值。Host字段反馈实际列入consumed_ids。结果原件modeler-round8-static-verification.json；这仍不是实际apply或独立L1通过。Coordinator已沿原scope接续整合（role-00008），费用约4.48275 CNY、余额1.51725。

### 实际写入完成：revision 2 / 143项

Coordinator `role-00008` 已实际采用唯一Ontology的空ontology_targets默认投影，更新为Modeler generation2/result2:8精确贡献并保留143项原作者。`apply-00009` 成功完成；真实平台快照 `1daaeea617204b1fbd911b42f19444d7` 确认同一Ontology revision 2，resource_refs=143、resource_bindings=143，model_read_error=null，role_application=1。此前apply-00006 not_written及原件不覆盖。143项经现有compiler分为2批执行，不等于2轮业务建模；还需核对应用回执及实际治理正文，不能用2个revision增量当作质量通过。

当前根进入self_check，CQ处review，正式独立36项仍未执行。剩余约1.148 CNY；优先完成生产必要自查和正式L1，再视准入余额补整合过程诊断，避免可选诊断先消耗最后正式验收资源。整合诊断暂缓并不计通过，阶段覆盖保留unobserved；不从正式私有评分回填过程分数。无新预算申请或模型/effort变化。

### CQ读回刷新触发额外影响评估

CQ `cq-public--role-00003` 已完成实际revision2读回，13题问题/定义对象未改。原件public-cq-review-diff.json核对所有差异只位于unknowns（7条）与coverage_gaps（2条）：主要是补实际模型证据/修订、由“尚未模型验证”改为“已按revision2核对”，未变Q3/Q4编码未知及Q7/Q8/Q9来源缺口。问题文本与13题分母完全相同，不等于新增业务需求。

_refresh_cq当前按整个artifact比较changed，因此仍给Modeler投递“New exact public CQ version; determine its effect within your scope”普通输入；实际投递到modeler--role-00010，原self_check receipt则仍按phase=self_check queued。原Modeler先进入propose影响评估，根专用check_unit因其当时非proposal_ready触发unit_check_not_ready，转回等待子级；此时没有实际unit_check LLM报告，不能说原作者自查已经完成或语义失败。保留这次状态/回执与代码路径；尚未修改调度，也不把新的影响评估当作新的业务修模轮。是否将proof刷新交给原作者自查并避免额外propose，需依据最终no_change/修改结果区分，不能靠Host猜文本语义删通知。

`modeler--role-00010` 实际返回no_change（candidate=null、changes=null），不是重建143项。其记录/卡片明确新版CQ仅实际支撑证据更新，业务范围/共享定义无变化，并在实际revision2上做73项资源清单、35项关键实体/属性正文和8个映射的责任范围治理读回，原未知保留。该读回是生产侧自述及治理读取证据，不是专用unit_check报告或正式独立L1。当前Coordinator进入role-00010整合此no_change；资金约5.45785/余额0.54215，物理模型仍revision2，没有再次申请写入。

Coordinator `role-00010` 拟用contributions=[]收尾，但check_units=[modeler]，实际触发original_owner_check_missing（owner_work_ids=[]）。Host交回精确技术约束：当前composer允许选择Modeling角色的no_change结果（candidate_ref/changes_ref=null、selected_change_ids=[]），由此保留check_units原属主；CQ无候选贡献不合法不代表Modeling no_change贡献不合法。不得重选旧143个create。原模型revision2未受影响，原进程进入role-00011纠正。后续[耗时复盘](2026-11-04-demo-role-high-flow-retrospective.md)核对原始时间戳纠正了先前“在忙碌边界前”的表述：role-00011已于12:04:40.405Z开始，host-nochange-owner-selector-20261104在12:05:15.856Z才queued，最终未delivered/consumed；不能将role-00011的正确选择归因该条Host指导。此为空变更收尾合同采用失败，不是新模型质量结论。


### 第二次预算停稳与原属主自查路由修复

Coordinator `role-00011` 已正确选择Modeling generation2/no_change的精确贡献，不再重复143个create；随后真实触发 `unit_check_scope_forbidden / unit_id=modeler`。根最终paused/activity=model/round13，控制active={}。实际Modeler已接纳proposal含review_units=[modeler]；它是无子级的自身冗余检查声明。`check_unit`原逻辑只允许direct_units，故在本人的专用治理读回之前拒绝。该失败归为platform-contract，不能据此判模型业务语义错误。

T0复核：原属主本人的检查在check_unit下半段无条件执行，因此自列不是越权访问，也不需要递归调用自己。收窄为从子级递归列表排除当前unit_id；其他非直属子级仍拒绝，原成员身份、generation、精确候选、实际模型revision、来源和治理读取证明均保留。本次只改unit_checks.py两行含注释，不改变实际候选、业务字段、Ontology拓扑、预算门或独立验收标准。不另建框架、不删除整体范围守卫。

GitNexus impact未索引到check_unit（UNKNOWN），detect_changes也未覆盖这段v5代码；不能把其空影响结果当作图覆盖。以实际调用点替代：flow._review_children、CLI check-unit及自身递归；回归覆盖自身、子级、自查证明复用、修改回退和错误恢复。先新增真实已接纳proposal形状的测试：修复前冗余自身用例以unit_check_scope_forbidden失败，越界用例通过；最初测试曾在legacy提案入口提前被旧合同拒绝，调整夹具为已接纳proposal后才复现原失败层。修复后test_unit_checks.py的20项全部通过（46.76s）。正确测试目录下完整v5回归411项通过、1条依赖警告（866.47s）；Ruff和git diff --check通过。工程验证不等于真实语义验收。

当前原CLI已自然退出；下次获准resume会重新加载修复模块，沿同一run读取原检查点。因预算关闭，尚未发起修复后的真实专用unit-check或根整体检查，故不声称实际阻塞已解除。未调用stop/cleanup、未删除已写模型或会话；保留原scope及生产访问以便按同一账本安全接续。最终平台快照9866b76de11f498db600bbb2cdea54e6：原Project/Ontology不变、revision2、143项resource_refs/bindings、model_read_error=null；独立包SHA仍沿原冻结值，未向生产泄露隐藏题或答案。

### 6元授权截止统计与验证边界

同一账本原3元+用户明确批准追加3元=6 CNY；最后一个已准入回合自然收尾后估算6.03286852 CNY，超额0.03286852，remaining=-0.03286852，admission_open=false、paused_confirmed、inflight=0、pending_settlement=0。不是新获准支出或提供商最终账单；没有继续追加预算或开启新付费回合。19/19已知托管调用计量完整，无缺失用量；外部Host/未接线辅助调用用量未知，单列且不计任务扣款，不按零估算。

| 角色 | 原生调用 | 输入tokens | 输出tokens | 缓存输入tokens | 原生区间并集秒 | 估算CNY |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coordinator | 9 | 5,582,223 | 404,573 | 4,566,272 | 7,671.217 | 2.72556844 |
| Modeler | 6 | 9,044,699 | 413,002 | 8,192,576 | 7,859.882 | 2.66798252 |
| CQ | 2 | 1,608,960 | 59,612 | 1,416,000 | 1,199.744 | 0.45972800 |
| 过程评价 | 2 | 101,887 | 33,569 | 57,728 | 732.758 | 0.17958956 |
| 合计 | 19 | 16,337,769 | 910,756 | 14,232,576 | 不逐角色相加 | 6.03286852 |

输入含缓存，输入+输出=17,248,525 tokens；缓存不能重复加总。原生窗口2026-11-04 05:37:20.646—12:15:16.989 UTC（新加坡13:37:20.646—20:15:16.989），23,876.343秒=6时37分56秒，含第一轮预算暂停后的长等待。全部生产原生区间并集15,829.118秒=4时23分49秒；过程评价与生产重叠，全部调用并集也为该值。原生区间含工具/provider等待，不等于纯语义推理有效时间；Host、harness/文档的有效劳动时间未完整计量，不做净降耗判断。新增工程回归耗时单列，不混入上述生产窗口。

过程评价仍只完成切片与CQ两点：切片四维4/4/4/4，CQ为3/4/4/4，均保留低优先级gaps；整合点未观察，未为补齐评分而占用最后正式验收资源。正式L1未执行，不是36题失败。实际unknowns（编码、时间格式/时区、事件/历史与操作者来源缺口）保留，不能用虚构答案补齐。

| 验证对象 | 本次截至6元停稳的证据 | 结论 |
| --- | --- | --- |
| 专职职责采用、F1—F5 | 独立Coordinator、Modeler、CQ上下文及精确交接已采用 | 局部真实通过 |
| 组合及实际apply、F6/F7 | 143项原作者组合、唯一已授权Ontology投影、application完成、rev2实际快照 | 已观察；不代表业务语义通过 |
| 自查/恢复、F8—F10 | CQ读回完成，Modeler另有生产读回/no_change；专用unit-check路由失败并局部工程修复 | L0仍未闭环，修复后真实恢复待授权 |
| 独立质量、A15 | 隔离36项冻结标准；尚未handoff/evaluate | L1未验证，不能保证建模质量 |
| 复杂多Modeler/递归及重复性、A3/A16 | 当前只有一个Modeler承担两关联切片；无第二同条件运行 | 未覆盖，不能宣称普遍多Agent质量或L2通过 |

最新原件：status-before-unitcheck-repair.json、snapshot-final-six-cny-paused.json、process-report-final-six-cny.json、observed-usage-summary.json、usage-final-budget-pause.log及unitcheck-repair-full-regression.log，均在本次inputs目录。此前失败及3元截止原件不覆盖。获准继续时优先原属主专用读回、根整体自查和冻结36项独立验收；不重建模型、不重置账本、不以过程分数代替L1。追加金额仍需用户新的明确授权，测试和快照不隐含付费授权。


工程回归命令纠错：首次全量命令只给-c配置路径，未显式给测试目录；从仓库根运行时pytest因此递归收集历史workspace副本，221.71s后报告5512个收集错误。该轮是Host测试命令范围错误，不是当前v5套件或模型失败；原日志unitcheck-repair-overbroad-collection.log保留。已改为显式 `pytest -c modeling_team/v5/pyproject.toml modeling_team/v5/tests --tb=short -q`，同一依赖/PG配置；只以后者判断完整v5回归。


最终工程结果：显式modeling_team/v5/tests范围 **411 passed, 1 warning in 866.47s**。唯一警告来自pydantic_settings的lifespan未解析forward reference（test_material_ranges_preserve_version_and_exact_source），不是失败；本轮未修改该依赖。定向20项通过、Ruff通过、两份文档84个本地链接/16张表格/代码围栏及diff空白检查通过。19个实际原生线程的(model, effort)集合仅(glm-5.3-flash, high)。本次只变更建模CLI模块及测试，不涉及backend/frontend，无应用服务重启；新CLI导入修复不等于已完成真实续跑。修复技术通知以host-unitcheck-self-routing-repair-20261104留给原Coordinator，不添加预算、不改变业务内容、不自动触发原生调用；消费与真实修复效果留待获准接续核对。
