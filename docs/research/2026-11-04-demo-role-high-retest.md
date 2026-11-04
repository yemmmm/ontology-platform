# 修后 Demo 专职多 Agent 建模测试

日期：2026-11-04。目标：验证 R5.0-012 修后真实专职协作和完整 Demo 建模质量。

来源：[R5.0-012/011](../requirements/requirements-v5.0.md)、[修复记录](../delivery/records/2026-11-04-role-team-live-contract-fixes.md)、[v5 runbook](../../skills/modeling-dev-loop/references/v5-runbook.md)。

配置：scripts/modeling、role-team/v1；所有托管生产、过程评价与独立评价均 glm-direct/glm-5.3-flash/high；独立 3 CNY 金额预算。一轮新建模，不沿用旧项目、候选或 PASS。复用上一轮冻结 Demo 原文、API、Schema 和公开 CQ；36 项原独立标准隔离保留，生产不可见。evaluation.model_read_scope=whole_model。

输入：`workspaces/v5-runs/demo-role-high-20261104-inputs`；运行：`workspaces/v5-runs/demo-role-high-20261104-start1`；代码：`365f6db`。其他工作树改动保留。

**截至本次交接：PARTIAL，金额预算暂停已停稳。三个专职角色、公开 CQ 和 143 项候选整合已实际采用；停在 apply 前，实际模型 revision 0。L0 未闭环，正式 L1 0/36 项执行、质量未验证，L2 未执行。** 公开 Demo 不构成客户业务盲测或普遍质量保证。

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
