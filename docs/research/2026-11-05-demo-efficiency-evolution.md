# 完整 Demo 建模效率阶段

日期：2026-11-05。状态：执行中，尚未形成效率或语义结论。

本轮用户要求先提交并推送工作区，然后以 project-evolution 推进项目；短期目标为 Demo 半小时内完成，总预算15元。初始工作区7个文档已提交797cfe0并推送origin/main。

权威依据：[R5.0-007](../requirements/requirements-v5.0.md#r5-0-007)、R5.0-012及[R4.3-030](../requirements/requirements-v4.3.md#r4-3-030)。沿完整Demo v2两业务切片、原始来源、公开draft CQ和36项冻结标准，不使用最小链替代Demo。

运行配置：新隔离run `demo-efficiency-20261105-start1`；首轮沿最近Demo的GLM-5.3-flash/high，后继采用仓库默认low作配置对照；role-team/v1，并发2。可选过程评价关闭，优先完整生产和最终独立验收。与此前开启过程评价的试验有配置差异，不能直接作单因素降耗归因。

本轮唯一15 CNY账本及详细阶段约定见[运行输入](../../workspaces/v5-runs/demo-efficiency-20261105-inputs/stage.md)。生产、独立验收、失败和修复沿同预算累计，外部Host单列。旧run及原预算不恢复。

完成标准：实际应用及治理读回自查，独立36项验收，完整闭环墙钟不超过30分钟。生产、验收、技术修复、等待时间分列。一次通过不证明L2稳定性，未执行独立验收前不宣称质量通过。

验证范围：初始文档本地链接、凭据模式检查及git diff格式检查通过；未改应用代码，无需服务重启。运行进展及最终用量待补。

## 首轮结果与窄修复

首轮high从14:03:59 UTC开始，超过30分钟仍未应用，效率目标REVISE，L1未执行。14:37左右请求自然边界暂停，后已停稳，保留候选与失败原件。未以空模型判断语义质量。

`demo-efficiency-20261105-low-start2`沿同task_ref、同15元账本及相同完整来源/36题标准创建独立模型范围。改变effort，不能称为同配置工程净降耗。首份候选约8分钟交付，完整结果待验收。

真实失败：CQ将published handoff引用作为最终artifact_ref，得到role_artifact_reuse_forbidden；原反馈优先描述submit_role_artifact，但CQ没有该工具。最小改变仅按实际工具能力返回可执行反馈，并在权威CQ提示中明确首次完整正文、引用复用及消息ID/材料ID区别。没有放宽来源、身份、实际消费或候选接纳校验。已向原CQ投递署名technical-host指导，不把现场指导当作新冻结包自动采用。

开发验证：新增真实WorkUnitFlow/PostgreSQL回归先复现失败；修后test_output_contracts.py与test_role_team_flow.py共18 passed、1既有warning（96.94秒），Ruff检查/格式和git diff --check通过。仅修改modeling_team，无应用服务重启。GitNexus未找到当前model符号，detect_changes返回0符号；按直接调用点及差异/测试核对，不宣称图谱覆盖。

诊断证据：并行CQ可在provisional scope启动，范围安装后按新basis重评；本轮确有新增问题/未知，不能全部判为无效重复。业务消息在最终信封接纳前也能触发其他角色重评。保留现有协作语义，不为本次效率目标引入事务消息或新编排框架。

## 15:29 UTC 阶段更新

- high已停稳，托管已知输入4,124,560、输出222,009（合计4,346,569，缓存含在输入，推理含在输出），无原生用量缺项；模型未应用，快照与失败保留。cleanup撤销全部临时钥匙并删除空scope，不能称可直接resume其已删除scope。
- low同样超过半小时，阶段效率REVISE，L0/L1尚未闭环。已完成来源、公开CQ、候选整合尝试；apply均返回not_written。失败从选择字段、候选正文语法到材料消费信封分层记录，未当作模型质量结论。
- 正在完成现有submit_role_artifact的静态请求预检，以及复用既有编译合同的候选value/semantic_definition工具指导。不执行新dry-run或平台调用，不放宽应用门；既有direct compiler 38项、受影响v5 34项及新增4项通过，完整v5回归进行中。
- 回归暴露新增pure compiler导入缺少sandbox挂载，low Modeler00019已native_turn_failed且无在途。归因为本次工程修改的runtime/infrastructure缺口，待补齐明确文件并通过真实MCP加载后同run恢复；不能把此失败判为模型质量问题，也不能把普通单元通过当隔离通过。
- 当前累计计价约2.82240544 CNY，余额约12.17759456 CNY。外部Host token unknown且不计任务金额。技术指导首次错误署名technical-host被原合同当业务答复纳入basis，原件保留；后继已使用约定host-technical，不改写历史。

## 工程修复验证（15:43 UTC）

静态请求预检复用direct_modeling原校验，允许v5候选待Host填candidate_ref；原compile默认严格要求不变。submit_role_artifact可在同一回合返回model_changes_invalid。工具指导复用现有fields/semantic_definition合同，宽松最终decoder仍保留聚合反馈。仅显式挂载pure compiler及两个必需合同JSON，不暴露整仓库或隐藏材料。

- 初始全v5回归：450 passed、2 failed、1既有warning，978.40秒；两个失败均为新增导入缺失造成的真实隔离加载失败，原件full-v5-regression.log保留。
- 补齐挂载后，原参数化test_candidate_validator_is_available_in_real_isolated_tool_process[False/True]均PASS，2 passed/4.71秒，见运行目录isolated-validator-final.log。
- test_codex_agent.py：5 passed/4.91秒。新增静态预检/指导测试4 passed，既有direct compiler测试38 passed，相关输出/团队回归见同轮执行证据。没有把450+2拼称一次全套PASS；受影响原失败已复测。
- Modeler新回合已实际启动，错误从数百项字段问题收敛至8处引用并完成新交付，Coordinator整合中；未取得应用/独立验收成功证据。原失败、修复与等待均计入本任务墙钟。

授权收到时间采用宿主分钟级估计；精确效率计时使用原生semantic start记录，不拿prepare或新线程时间重置旧失败。

## 2026-11-06 接续（16:22 UTC／00:22 Asia/Singapore）

low原子apply实际completed，无错误，revision1／55项绑定。CQ治理复核及原属主unit check完成；第一次整体自查曾ready，但后续全范围实际核对发现回放条件、凭证状态影响、调用步骤、额度边界、接口响应字段等语义缺口，生产ready不能作为最终接受。原Modeler已在原run开始实际修模，按建模轮次另记一次；此前格式/参数/材料消费纠错不重复计轮，semantic-start原生记录数不代替业务轮次。

应用后的no_change交付还曾缺贡献artifact，已沿原责任补齐最小无写入贡献并在权威Modeler提示明确，实际运行已接纳，不重放旧create。新引用需整体重新接纳，旧创建贡献不代替新no_change。当前无独立L1结论，效率REVISE；累计托管计价约5.04017612 CNY，剩余约9.95982388 CNY。修模、自查与独立评价继续沿同15元预算，不启动新账本。

## 16:52 UTC 更新

原Modeler在原scope采用fields-only更新：先6个update/0 create补充真实语义缺口，再1个update/0 create补充其治理检查指出的遗漏未知项；实际应用完成，未重放旧创建。原属主检查两次明确给出revise但返回Markdown清单而非JSON，原件保留。已在unit_checks动态提示及权威modeler-self-check明确单个JSON信封、格式重试保留判断/证据；20项unit check回归通过（51.28秒），实际后继检查已将revise交回原Modeler并取得上述1项更新。原检查与修模不是独立L1验收。

Coordinator首次仅重开单元未传具体7项发现，Modeler错误返回no_change；后继具体工作请求促成6项更新。权威Coordinator提示补充发送精确来源/实际表达/自查引用并核对后继贡献，不把单纯reopen视为交接完成。当前仍为原任务生产闭环，累计托管估算6.26715600 CNY，剩余8.73284400 CNY。

预算中内部辅助调用尚有unwired_auxiliary=unknown，外部Host token同为unknown且排除任务金额；不能将托管账本估算或缓存率当作完整全任务成本或净降耗证据。

## 17:52 UTC 更新

修复后冷启动demo-efficiency-20261106-low-start3于2026-11-05T16:58:59.624259Z实际开始，原完整材料、low、36题及同15元预算。实际scope-plan已采用Modeler正式提案依赖cq-public，CQ无反向依赖；但先遇CQ Q8/Q9同时列入复用/修订、changes.schema_version错误、Coordinator shared_refs漏填及正文编译错误，超过30分钟仍未完成应用，效率REVISE。没有用缩小范围或旧模型替代冷启动。

CQ分类拒绝现补充重复/缺失/多余的确切ID反馈，保留原唯一身份与完整分类校验；真实失败包确定重复仅Q8/Q9，定向验证仍拒绝原错误，既有角色流程2 passed/58.86秒。

本轮工具指导还发现工程回归：将底层operation字段并集用作封闭candidate.value白名单遗漏合法relation.value.predicate。已改成开放的生成指导、显式predicate与各类型关键字段/端点说明，保留实际候选/编译校验。新增合法property谓词+关系的同一正例通过真实compile_model_changes和guidance JSON Schema，5项通过；扩展角色测试113 passed/464.88秒。不能将该指导缺陷归为模型质量问题。

旧run收口并非预算/锁故障：Coordinator收到proposal_ready的no_change结果，却将“尚未纳入current contribution_refs”误判为Modeler仍pending，并因无新队列消息等待。保留精确贡献与材料消费门，通过技术工作提示解锁；权威Coordinator提示补充生命周期active与工作ready、待整合与未完成的区别，不新增平台硬门。

运行控制已交单一trial_runtime_owner，父Host仅做只读核对和工程修复；其独占两个在途run的CLI控制，继续沿原授权到真实handoff与原生独立评价。当前L1尚未执行，已知托管估算约8.35/15 CNY；Host与未接线辅助用量边界保持。

## 18:23 UTC 元数据复核与恢复

独立只读方案审阅PASS、无Critical/High及关键未决假设后，执行两项T0窄修复：源版本不变量继续由read_material实际SHA校验和既有_source_was_read证明保护；只有批准material ID的当前版本读取成立，才将LLM回填SHA校准为真实manifest SHA，未读/错版/未知ID仍拒绝。RawNative与原读取事件不改。旧执行的作者、完成状态及同基线复用筛选不扩大。

Modeler changes归一化只深拷贝技术envelope：缺schema_version填冻结v1、缺candidate_ref填Host后填的null，去掉无执行效力的顶层request_id；显式错误版本、未知字段及业务value/item/target仍交原严格decoder/compiler拒绝。公共decoder与direct compiler未改，legacy路径未改。

新增18项真实PG RoleActors/WorkUnitFlow正反测试；最终定向组合79 passed/243.29秒，1条第三方warning，Ruff/diff检查通过。另两项stale-feedback测试及15项相关角色测试证明仅刷新已消费的model_input_pending提示、不改历史state。代码源调用点核对；GitNexus没有当前符号，不宣称图谱覆盖。

此前单执行者交接没有持续按任务执行并返回“未收到任务”，已保留协作失败，父Host核对无在途后收回唯一控制；没有声称仍在后台推进。两个原run均已用新CLI进程续接以核对真实采用，应用/读回/独立L1仍分别取证，未将测试或审阅升级为业务PASS。

## 18:48 UTC 新回执与协作阻塞

两个续接进程均自然返回，预算在途/待结算均为0，累计计价10.23153800 CNY，余额4.76846200 CNY。旧run原Modeler最新no_change已被Coordinator准确纳入composition，但pending_units仍读取复用工件的旧changes_ref（上次已应用的两个update），将新no_change的result_ref与历史application origins比较，误报unfinished。新run apply-00018为确定性部分应用：前三批28项applied、第四批7项not_written；application_failure只认整体not_written而未交接实际回执，原Modeler两回合waiting_peer索取同一回执。两项均为platform-contract/collaboration反馈缺口，不能归因于模型质量，计划只修当前状态判断/原作者回执交接，不重放已应用批次。

Coordinator把Modeler team_material误放coordination_refs还触发KeyError；已收窄为coordination_reference_kind_invalid，准确给出实际/预期kind与合法contributions路径。新增负例1 passed/0.81秒，合法嵌套Coordinator及公开CQ路径2 passed/47.70秒，Ruff和diff检查通过；提交779fd22。GitNexus detect_changes本轮返回0 symbols（索引未覆盖这些新模块），影响范围使用源码调用点和对应测试核对。

上述开发证据未建立独立L1、半小时闭环或净降耗结论。当前完整阶段仍REVISE，原有36题及来源范围不变。

## 18:54 UTC 两项恢复实现及实际采用

修复已提交e5384bd：pending_units按当前no_change语义核对精确贡献已整合，不把其复用工件的历史changes当作新写入；真实proposed待应用、未整合no_change、非ready和旧generation仍pending。application_failure支持确定性partial：完整保留receipt/origins，以not_written批次change_ids补全原子失败批的责任人，准确提示只修未写入部分，uncertain/completed不交接、不新增写入。

先复现3 failed/11 passed；修后新增14项通过（11.80秒），既有role_flow_corrections/role_team_flow 15项通过（108.24秒）；Ruff及diff检查通过。实际复用helper向start3交接原apply-00018回执，未调用apply，Modeler重开generation7；两个run由新CLI接续，start3 modeler--role-00023已开始。旧run补充host-technical恢复说明，不引入业务事实。一次误发重复resume在初始化锁等待时已终止，仅原控制进程继续，无新增原生执行/模型写入。

对应PG测试及只读实据见运行输入目录role-application-progress-{red,green,regression}.log、role-application-receipt-read.log及partial-receipt-redelivery.json；这些是窄合同修复/采用证据，不是独立36项语义PASS。未修改backend/frontend，无应用服务重启；真实建模CLI已使用新进程。

## 19:17 UTC 后续两处实际恢复边界

旧run自查49-001真实返回全模型51项正文和四份来源，漏公开CQ；002只补CQ后又缺前四份来源，暴露每次单execution覆盖校验的重复读取。初版只合并同线程proof的单测通过，但实际001/002/003/004均fresh thread，不足以证明真实续接；已保留该实际差异，未把初版单测升级为采用PASS。最终dfd6769复用既有_correction_invocation：调用前筛选同作者/phase/generation/round/精确target及来源manifest/candidate基线的完成执行，校本地thread binding后沿最新原生上下文接续；调用后仍只合并相同真实thread的实际读取。当前turn仍必须governed read，来源全文/模型正文/关系完整门不变，旧无基线执行不追溯补证。两项局部checkpoint字段仅服务同基线纠错，不改公共execution/acceptance/evaluate合同。

- 初版新增13项/22.10秒及既有自查/角色生命周期7项/38.06秒通过；实际native接线修前2 failed/21 passed、修后23 passed/39.35秒。后者包含原13项和新增10项，不能重复计成36个唯一用例；实际CodexInvocation+mock transport覆盖resume_from、最新完成turn、usage baseline与缺/错binding及无效proof。原日志self-check-read-reuse-*保留。
- 旧CLI在相同缺口重复出现后沿自然边界暂缓、确认active为空再用新进程恢复；最后两项修复后已启动resume-low-18，仍待真实线程/交接取证。

新run原apply-00025在执行前被_close_applied_sessions拒绝旧apply18的确定性partial，目录仅intent/candidate/compiled，无execution/新提交。T0：收尾守卫保护未知写入及lease必要，但各批已明确applied/not_written且无批内partially_applied时，原executor可按原记录安全关闭session。5282ae4只放行该确定性情况，unknown/uncertain/批内部分写入/空partial继续拒绝；全bridge/CLI文件19 passed/9.92秒，原失败1项先复现。

随后实际resume仍被MultiUnitFlow的platform active门跳过：活动标记正是当前原apply ID。dd3f4c2沿已有原生执行对账模式，仅允许当前activity=apply、同unit、同round原apply ID进入原flow续接；不同ID/其它活动仍等待，不清控制状态、不新造操作。复现1 failed/2 passed，修后新增3项及既有multi_unit共8 passed/37.18秒。两个修复均Ruff/diff检查通过，调用点仅apply/finalize与CLI多单元调度；GitNexus未覆盖当前符号，未声称图谱覆盖。新run已沿原apply25通过resume-low-cq-first-8接续，实际结果待补。

本轮未改backend/frontend，无应用服务重启；必要新CLI/Host子进程承担实际采用。最新账本快照11.50911960 CNY，余额3.49088040 CNY；完整36题和半小时标准不变。

## 19:21 UTC 实际采用与首个独立评价启动

- start3原apply-00025实际completed，7项全部applied、errors=[]、pending_changes=[]；旧28项未重放。原CQ已刷新，Modeler消费实际回执中，仍属生产闭环。
- start2自查49-006实际沿49-005同thread `01a1ad1f-34ce-7aa2-bd32-eb65e24604fa`续接，native-usage-baseline明确source_execution=49-005及原累计用量；不是新thread冒称续接。随后实际handoff_ready、无在途（19:20:44Z观察）。这是原纠错读取循环解除及生产交接证据，不是独立语义结论。
- 已启动原生独立评价efficiency-low-start2-36，仍绑定同36题冻结包、实际模型revision4及原15 CNY预算；生产侧不读隐藏题/答案。最新已知计价11.67995592 CNY，剩余3.32004408 CNY。
