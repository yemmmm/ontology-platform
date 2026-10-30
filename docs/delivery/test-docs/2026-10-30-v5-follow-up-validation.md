# v5 后续任务验证与实施记录

日期：2026-10-30。统一计划：[v5 后续任务清单](../implementation-plans/2026-10-30-v5-next-tasks.md)。
风险依据：[高影响评估](../../research/2026-10-30-v5-high-impact-risk-assessment.md)；
基线核对：[流程一致性](../../research/2026-10-30-v5-modeling-flow-design-alignment.md)。

本文件是后续逐项追加的证据记录，D0 为初始登记，后续实际推进见各轮记录。
原基线 `c9f7171` 的既有证据不改写；本轮实施从 `4e41581` 开始。

## 任务状态

| 任务 | 关联风险 | 验证／定位 | 实施修复 | 真实采用／接续 | 独立语义 | 成本结论 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 状态、覆盖和去向 | R1、R3 | 缺状态、旧覆盖、导航／作者遗漏已复现 | 导航及自查上下文已修 | 新任务默认自查沿原记录闭合 | D5 有界六项 6/6；完整场景待联验 | 净收益未验证 |
| T02 按依赖分阶段应用 | R4 | 安全部分整层等待已复现 | 最小调度修正已验证 | A 先应用、B 后接续，身份保留 | 公开工程 4/4 PASS | 同条件降耗未验证 |
| T03 子单元闭环 | R4 | 格式、回执及父级材料交接均有复现 | 有界读回／重开、证明及精确读取交接 | 原 B 实质修模、A 复用，原身份保留 | 工程修模 4/4；多层／自主采用待验 | 净收益未验证 |
| T03.1 未知执行恢复 | R5 | 按实际窄窗口开展 | 待定位后决定 | 待验证 | 按影响范围判断 | 未验证 |
| T04.1 验收取证正反例 | R2 | 合格、规则遗漏及方向错误已验证 | 已补精确读取及证据识别 | 原生独立上下文实际读取 | 公开有界正反例正确区分 | 未验证 |
| T04.2 代表性完整语义 | R1、R2、R4 | D6 组合／父级／限定澄清与端点缺陷 | 身份适配及来源反馈已修，202 passed | 实际 revision 5；六端点对账一致 | 初始九题有漏查；负对照拒绝正确；最终十二题见 D6 | 净收益未验证 |
| T05.1 共享变化影响集 | R3 | 共享解释及遗漏依赖已有对照 | 已补方法指导 | 新上下文修订／重审已发生 | 公开工程范围 3/3 PASS | 未验证 |
| T05.2 消费、总览与接续 | R3 | D6 共享上限变化；D8 fork 身份交接 | 原单元修订及显式原生 ID 交接 | D8 新 fork 复用原类增量写入、进程接续 | 变化后模型 12/12、总览 3/3；D8 五题 5/5；撤回／未知恢复待验 | 净收益未验证 |
| T06 全任务降耗 | R4 | 已保留来源重复声明、格式纠正及根级往返 | 已修声明提示／精确缺项反馈 | D6 后继根级无同类缺项重试 | 同条件质量待证明 | 净收益未验证 |
| T07 状态与文档 | 各项 | 本轮已登记计划和风险 | 后续随项同步 | 不适用 | 不代表语义通过 | 不适用 |
| T08 记忆专项 | 按实际缺口 | 待开始 | 研究后决定 | 待验证 | 待验证 | 未验证 |
| T09 Schema 专项 | 按实际缺口 | 待开始 | 研究后决定 | 待验证 | 待验证 | 未验证 |

## 每轮记录要求

沿用本文件追加轮次，不新建按单次输出定制的验收器。每轮保留以下信息：

1. 日期、任务及风险编号；验证者／实现者／独立评价者职责与输入边界。
2. 代码提交或工作树差异、材料与 Profile 版本、模型／effort、实际模型 revision 和冻结标准；真实运行另记录授权来源、原 task_ref／budget_ref／run 和 operation 身份。
3. 本轮要核对的具体不确定性、原证据可复用部分，以及实际执行的只读检查、测试、模型／平台操作或修复。
4. 真实观察与预期差异、第一阻塞层；失败只沿 modeling-quality、platform-contract、collaboration/routing、runtime/infrastructure 分类，未定位时明确保留未知。
5. 证据路径／报告、实际调用及已知用量、有效语义／技术修复／等待时间、宿主介入和缺测；外部 Host 单列且不扣任务金额。
6. 分别记录开发检查、真实采用、独立语义及成本结论。使用 PASS／REVISE／PARTIAL／BLOCKED 时说明确切范围，未运行写未执行，不因完成了机械流程就消除风险。
7. 若实施修复，保留原失败、最小变更、对应复验和新实际目标；确认现有机制已经满足时，可记录无需代码改动。最后写清未完成项及下一动作。

## 登记轮次 D0：计划与风险归档

- 用户指令：将本轮发现的问题和前面计划写入文档，后续逐个验证和实现。
- 已完成：统一 T01—T09 任务入口，映射 R1—R5，提前 T04.1 验收取证正反例和 T05.1 共享变化影响集验证，补 T03.1 的窄恢复窗口；本文件建立逐项状态及追加记录方式。
- 原始证据：状态、流程核对和风险分析仍保留在 `docs/research/2026-10-30-v5-*.md` 的对应报告中；本轮未将其中风险推断升级为已经发生的生产缺陷。
- 本轮验证范围：文档链接、章节锚点、表格及 diff 检查。工程／真实运行／独立语义均未新增执行，不需要服务重启。
- 下一动作：后续实施先开展 T01 与 T04.1 的首轮有界验证，按真实结果定位和修复；当前风险均保持待验证。

## 推进轮次 D1：T01／T04.1／T05.1 首轮真实验证

### 授权、身份与边界

- 用户本轮指令：“请按照计划继续推进，你可以任意使用glm模型进行建模测试”。采用既有 `glm-direct／glm-5.3-flash／low`，首次真实原生建模已在本轮最小准备后开始，没有前置全面审计。
- 首轮同一任务 `v5-followup-20261030`，稳定金额账本 `workspaces/v5-runs/followup-20261030-inputs/budget`，沿默认 3 元人民币；没有将“任意使用 GLM”改写成无限金额或伪造结算。外部 Host 不扣任务金额，失败、恢复和评价计入同一任务。
- 原材料复用已接受动态树工程场景与表示决定，六题公开工程标准在生产前固定。生产 run 为 `followup-20261030-baseline` 和 `followup-20261030-improved-isolated`；原始失败与暂停均保留。它们不是完整业务盲测。
- 一次对照准备误共用 task 控制域，得到 `original_execution_active`，没有启动第二份原生执行；原目录 `followup-20261030-improved` 保留。随后显式使用独立 workspace_ref，仍绑定原预算，不改原冻结绑定。

### 已观察问题与最小修复

1. **T01 实际状态维护不足**：基线连续写入记录未传 states，并出现按回合重复建记录；补充既有 states、命题处置、稳定身份和精确 depends_on 的具体使用方式，没有新增语义必填硬拒绝。修订后的真实调用已填 review／cognition／expression／work，并登记精确依赖；完整模型交付及覆盖还需随后结果，不以填字段算语义 PASS。
2. **prompt-contract／platform-contract**：最小新 Task 的冻结合同只带 change／candidate／semantic_definition，漏了完整 Class／relation_type 请求示例；GLM 连续用 request_id 代替 schema_version，反馈仅 model_changes_required。补冻结示例及路径、期望值和纠正说明；两项新增用例先失败后通过，原响应不改写。
3. **输入身份反馈不清**：技术主动输入曾被误填为 resolved_request_ids，沿原输入／请求检查保留阻塞，补明确反馈“消息身份不是问题身份，无实际问题则 []”，未放宽确认规则。
4. **真实读取缺口**：规则遗漏反例初次评价将一个已存在关系记为未读取，不足以判断模型缺失。v5 原生工具缺少精确资源展开，新增只读 `read_model_resource`，复用现有治理 read-model 接口、范围、只读 key 和冻结 revision；未修改 backend／frontend。
5. **T0 收窄读取证明守卫**：方向错误反例已逐资源精确读回，但原守卫只承认 query_semantic_context，导致 actual_governed_read_missing。精确读取同样保护真实治理读取不变量，故接受其真实本体／版本观察，仍要求覆盖冻结的全部本体。新增缺一／齐全两项用例；对原完成的独立原生结果重解析，无新模型调用、未改原事件或原报告失败记录。

### 独立公开工程正反例结果

| 目标 | 控制方式 | 原生独立结果 | 证据与边界 |
| --- | --- | --- | --- |
| target-a | 从已验收工程意图复制完整三 Class、两关系及全部条件到新自有项目 | 6/6 PASS | `followup-20261030-target-a/evaluations/evidence-control-a/` |
| target-b | 仅删去安装定义中的临时可用例外及允许模态 | 初次 3/6 PARTIAL；补精确读取后 4/6 PARTIAL | 两次报告均保留；后者只在预期缺失的题 4／5 未通过，模型未修改 |
| target-c | 保留文字定义，但反转核验关系的真实源／目标 | 5/6 PARTIAL | `followup-20261030-target-c/evaluations/evidence-control-c/`；题 2 未通过；保留技术守卫原错误及重解析回执 |

这些为 Host 制作的明确工程正反例，制作上下文没有担任语义评价者；评价者均为全新隔离只读 GLM 上下文。Host 仅制作冻结目标、调用及技术校验；手工准备的 fixture handoff 不作为生产流程／生产自查 PASS。
结果证明该模型和场景中能区分已知遗漏及结构方向错误，不代表所有题集、模型或复杂业务都不会误判。过期定义等其他范围继续保留未验证。

### T05.1：RDF 不变时的共享解释及影响复核

- 在 target-a 的同一工程项目创建明确待复核的错误解释样本及精确依赖的覆盖／摘要，并留无关设备定义作对照。实际模型原先已经正确，不由记忆补写事实。
- 第一个真实 GLM 上下文据原材料纠正共享决定：决定 revision 1→2；已有覆盖／摘要 revision 1 自动 needs_review；无关定义保持 revision 1，RDF 始终 revision 2。
- 另加一个**在决定更新后制作**、缺少必要依赖的覆盖故障样本，实际 freshness 仍 current。这是显式反例，不谎称它由变更事件自动发现。
- 新 GLM 上下文按源材料及语义使用关系复核，刷新覆盖／摘要并修复未登记依赖的样本；相关记录成为 revision 2、current，无关定义仍 revision 1、RDF 仍 revision 2。已将“freshness 只覆盖已登记依赖，还须按需查语义使用者”写入权威方法提示。
- 额外范围在评价前冻结，以转换原件为待验产物，由新只读上下文核对来源、实际模型和前后记录，**3/3 PASS**。报告 `followup-20261030-memory-impact/evaluations/shared-impact-check/`，scope_id 为 `v5-shared-interpretation-impact`，保留原六题 base_freeze_id。
- 证据：`followup-20261030-inputs/memory-impact-before.json`、`memory-impact-after-update.json`、`memory-unlinked-control.json`、`memory-impact-after-review.json`。不能将受指导的工程查证外推成未知依赖自动完备发现或全业务长期保真。

### 开发检查与继续位置

- 初始状态／合同范围 **19 passed**；请求示例与反馈修复相关 **29 passed**；精确读取、验收和原生工具相关 **26 passed**。
- 第一遍完整 v5 回归出现新增只读工具清单断言未同步，原失败保留；修正清单并确认只读注解后，完整回归 **177 passed、1 条既有第三方 warning、216.18 秒**。此后新增精确读取证明及 T02 调度修改，最终需覆盖这些新增差异，不能直接沿用该数值作为最终代码 PASS。
- T02 已用确定性用例复现 A 已完成、B 等待时完全不应用；正在验证“安全组先应用，但未完成子级仍阻止整项目 handoff”的最小修正。真实 T01 生产链也继续按原目标修正表达，不因只创建 Class 就收口。
- 所有原始命令输出、原生身份、回执和用量保存在 `workspaces/v5-runs/followup-20261030-inputs/` 及各 run；尚无同条件净降耗证据。正式最终回归、资源收尾、用量汇总和后续任务状态将继续追加。

## 推进轮次 D2：T01 的写后错误与独立工作空间审计

### 第一阻塞与修复

- **platform-contract**：真实 GLM 将 material 引用或包裹后的 reference 写入 depends_on；旧工具先持久化，再在 freshness 取 record_id 时 KeyError，导致后续读取也失败。新增四项失败用例后，改为写入前返回有路径、所需字段和纠正方法的 `invalid_dependency_reference`。已有坏记录仍可读取，freshness 标 needs_review 并列出 invalid_dependencies；不要求删除失败记录，不把格式错误升级为 run 死亡。
- 该守卫只保护可读取的引用合同，不判断业务依赖是否完整；未声明的语义依赖仍须由 Agent 查证。相关 **32 passed**，旧坏记录、初始 red 输出均保留。
- `followup-20261030-improved-isolated` 最终真实 handoff_ready，模型 revision 2；首次独立输出因 JSON 字符串引号未转义失败，保留原件并补提示。新独立只读上下文对同一冻结六题得到 **6/6 PASS**，见 `evaluations/complete-model-check/`，目录内保留格式失败及重试，最终报告绑定原 freeze_id 和 revision 2；这只证明公开工程模型忠实度。

### 工作空间单独评价

- Host 没有将 6/6 模型结论当作 workspace 完整结论。原始记录导出、两次 GLM workspace-only 维护均保留；只更新工作空间，没有改 RDF，也不把生产自查当验收。
- 补充三题在评价前冻结为 `v5-workspace-audit-20261030`，base 为原六题；新独立只读 GLM 核对原始来源、实际模型、task／project 导出。首次 **REVISE，2/3**，`evaluations/workspace-final-audit/`。
- 失败明确定位：task `r4-3-025-coverage` revision 1 仍 applicability=current、expression=partial、work=needs_expression、model_basis=0，与 revision 2 的实际完整模型及另一当前 task coverage 冲突；只修 project 摘要漏掉了它。不是模型缺少关系，也不是因为历史记录存在就失败。
- 将检查相关 task 与 project 记录、明确取代旧覆盖写入权威方法；沿原任务、原模型 revision、原预算由 GLM 做窄工作空间修订。原审计和失败产物不覆盖。后继独立结果在本记录末尾追加。
- T01 保留边界：这些维护包含明确 Host 技术提示及审计反馈，不等于新任务默认自主维护已普遍成功；未分配父级范围与复杂业务低频例外仍按 T04.2 验证。

## 推进轮次 D3：T02 分阶段应用与 T03 有界自查

### T02 真实阶段证据

- 独立任务 `v5-partial-application-20261030`，账本 `workspaces/v5-runs/partial-20261030-inputs/budget`，金额 3 元；不是给首轮账本清零。其目标是明确公开的 A/B 分阶段工程测试：A 为已知名称的共用设备 Class；B 为名称缺失的结果记录 Class，两者无业务依赖。
- run `partial-application-20261030-start1`，两个原单元 `ready-object`／`pending-record`，生产前冻结四题 `v5-partial-public-20261030`。仅此场景允许 Host 作为测试名称提供方；补充署名为 `host-engineering-fixture`，没有冒充用户真实业务确认。
- 原调度把全部直接子级列为父级依赖，确定性用例重现 B 等待时 A 无法应用。修正后只按显式必要依赖排序，根级可提交安全组；未完成子级仍阻止最终 handoff。原有真实组合依赖的 fake parent 明确返回等待，保留“必要依赖不能越过”断言。
- 实际 phase1 为 revision 1，A 已应用，B 仍等名称，父级未 handoff_ready；`phase1-proof.json` 保存实际快照、工作状态和两个问题。原根级曾重复 B 的名称问题，补“不要重复待决子级问题”的提示；两个已存在问题都保留并署名答复，没有删除重复历史冒充已去重。
- 补充 B 名称后同一 run 接续至 handoff_ready、revision 2；A 的原 resource binding 完全相同，只有两个 Class，无关系／实例。`prepare-phase-evaluation.py` 在独立前核对身份并冻结 phase-history 产物，原四题未改。
- 独立新只读 GLM 评价 **4/4 PASS**，`partial-application-20261030-start1/evaluations/partial-delivery-check/`。阶段证据证明 A 先应用和准确未决，最终模型证据证明表达；不把工程 fixture 当复杂业务整体通过。

### T03 当前实现和真实采用

- 新增 `check-unit` 和父级 self-check 的可选 `review_units`：沿原工作单元、原候选、来源 digest、work generation 和实际模型版本启动有界生产读回；只读 RDF，工作空间可维护。Host 保持唯一模型执行方。
- 生产检查结果保存精确版本证明和可供父级读取的材料；同一基线复用证明，不额外唤醒；非 ready 重开原单元和祖先，下一建模回合能读取 previous_local_check。父级仍负责跨单元规则和未分配范围。
- 两个原单元真实治理读回都 **ready**。A 一次完成；B 首次受“子级永远返回提案”旧提示干扰，返回 proposed；分离 modeling／self_check 目的后，下一次又将历史答复 ID 错报为本轮 consumed。守卫未放宽，补历史输入区别及结构化 allowed_ids／unexpected_ids 反馈，原单元第三次自查返回 ready。原始两次失败均保留；模型 revision 始终为 2。
- 随后对 B 再调用复用同一 execution_ref，未产生新原生回合。`check-pending-record-retry2.log`、`check-pending-record-cached.log` 可直接对照；A 见 `check-ready-object.log`。
- 开发用例覆盖缓存失效、局部 revise 重开原身份及祖先而无额外写入、父级请求直接子级检查、未知单元、阶段提示和同单元回执纠正。**真实局部实质语义修模、多层递归、自主选择 review_units 的采用仍未验证**，不能仅靠机械用例关闭 T03。

## 本批交付检查与范围

- 最终 v5 完整回归：**191 passed，1 条既有第三方 Pydantic warning，139.23 秒**，`followup-20261030-inputs/final-regression.log`。覆盖最终 Python 代码；随后仅加双 scope 方法提示和文档，不改变运行代码。
- Ruff check／format check 覆盖 v5 src、tests、host；diff 与本批文档链接另作检查。不修改 backend／frontend 或应用共享配置，不需要应用服务重启。
- GitNexus 前置 impact 未找到新增 v5 符号；detect_changes 只映射到旧文档符号，不能声称 v5 图谱影响覆盖。实际以已知调用点、差异检查、完整 v5 回归及上述真实链路核对。
- 净降耗保持 **未验证**。本轮确实减少了已证实的格式歧义，但 baseline 与 improved 包含不同纠正、暂停和 Host 介入，不能拿 round 13 对 round 6 宣称同条件节省；失败、生产自查、独立评价与维护全部保留在账本内。
- 时间口径：本轮首个真实 semantic start 约 03:07 UTC，后续持续穿插生产建模、独立语义评价与窄修复。精确有效人工技术／文档时间未单独计时，不能补造比例；原生 duration 可累计但并发重叠不能当墙钟或全语义时间。若下一阶段语义有效时间不足一半，按 AGENTS 暂停扩展平台／harness，走更短通路。
- 当前仍待 T03.1 的真正未知执行对账、T04.2 的 A19—A22／重复性、T05.2 的变化后消费及 T06 同条件成本，T08／T09 仍为后续专项。本批不宣称完整 v5 方法／完整业务盲测／净降耗验收 PASS。

## D2 追加：同标准复验与取证反馈修复

- GLM 沿原 workspace-closure 身份修订遗漏的 task coverage，明确标为已取代并登记当前保留记录的精确依赖；RDF 始终 revision 2。原工作空间审计的完整产物副本保留在原评价目录。
- 第一次后继评价因没有直接 read_material 读取一份原始资料，被原守卫拒绝为 `evaluation_original_source_not_read`。产物里的摘录不替代直接原始来源读取，也未将该原生报告中的自报 PASS 发布为有效结论。
- 实际定位为 prompt-contract 及反馈信息丢失：评价 prompt 原只列混合 materials，没有单列必读 source_ids；已有 FrameworkError.material_id 被 `str(error)` 丢掉。补 source_ids、明确逐项读原始材料，并将结构化错误原样保留到下次 contract_feedback；读取守卫与独立隔离未放宽。
- 两项新增原始来源反馈用例先失败，另两项格式重试仍通过；修复后取证与 CLI **28 passed**。再次沿同一评价 ID、同一三题 freeze、同一实际模型及修订后 workspace 产物，独立新原生上下文得到 **3/3 PASS**，`followup-20261030-improved-isolated/evaluations/workspace-audit-recheck/`。此前所有失败回合与原 REVISE 报告保留。
- 最新完整 v5 回归：**193 passed、1 条既有第三方 warning、135.32 秒**，`followup-20261030-inputs/final-regression-after-evaluator-feedback.log`。此前 191 对应提交 `d7340da`；后继 CLI 修复及新增用例由 193 覆盖。
- 首项稳定账本最终估算 **2.81229776 CNY**，剩余 **0.18770224**；其中已计价 **1.28235976**、四项暂估 **1.529938**，44 个计量单元，inflight=0，覆盖状态仍 PARTIAL，不能写为提供商最终账单。明细 `followup-20261030-inputs/budget-final.json`。所有失败、修正、自查和评价均在同一账本，没有追加或重置额度。
- T02 账本估算 **0.27195420 CNY**，13 个已知单元、无暂估，计量覆盖 complete；提供商最终账单未另行获取。外部 Host 与未接线辅助成本保留 out_of_scope/unknown，不扣任务金额，不补零。T03 实质局部修模是后续独立目标，另绑定 3 元，不沿用已清理 T02 run。
- 已停稳及 cleanup 的八个自有运行：baseline、误共域 improved、improved-isolated、target-a／b／c、memory-impact、partial-application。各回执均 `aggregate_keys_non_active=true`、`no_in_flight_attempts=true`；非空模型与证据保留，误启动且未写入的空项目删除。回执见 `cleanup-followup-20261030-baseline.json`、`cleanup-followup-20261030-improved-isolated.json` 和各 host/cleanup.json。此结论尚不覆盖仍在进行的 local-rework 任务。

## 推进轮次 D4：T03 原单元实质修模与父级材料交接

### 身份、来源和冻结

- 独立工程目标 `v5-local-rework-20261030`，run `local-rework-20261030-start1`，稳定账本 `local-rework-20261030-inputs/budget`，3 元。复用两 Class 场景结构，但本轮名称已知，目标是局部实际错误的发现与修订，不是给 T01 或 T02 账本清零。材料明确声明后续 Host 可能注入已知 B 故障，该操作不是新业务真相。
- 全部原生角色仍为 GLM Flash／low。生产前冻结四题 `v5-local-rework-public-20261030`，阶段产物在独立评价前固定；无客户盲测或用户真实业务确认。

### 已实际完成的局部循环

1. 两个原单元 `equipment`／`verification-record` 提案，父级首次应用并自查，实际模型 revision 1，两个 Class。期间根级误将 child 的业务提案形状当作 unified graph，`kind=class` 被编译拒绝，均为 not_written。GLM 最终自行纠正为 fields-only、candidate=null；补权威方法说明，子级提案不能直接复制为可执行图，不增平台业务裁判。
2. Host 只在自有工程模型上用明确 operation `host-inject-known-b-negation-defect` 改 B 的 business_meaning 为相反断言，revision 1→2；A 保留。原 intent、实际回执和快照保存于 `phase-before-local-check.json` 与 `fault-application-receipt.json`。
3. 原 B 实际治理读取后返回 **revise**：准确指出“记录存在即表示核验通过”违反原文否定，并与其 not_applicable 矛盾；其他字段无需改。程序重开原 B 与祖先为 generation 1，A 保持 generation 0，未额外写 RDF；`reentry-proof.json`。
4. 同一 run、同一预算 resume。B 原单元的下一 prompt 确实带 previous_local_check，并给出局部修订；根级只更新原 B，revision 2→3。A 定义逐字段未变，A／B 实际身份都保留，仍只有两个不同资源 IRI，没有重建同名 Class。
5. 根级整体 self-check ready；Host 显式安排 B 原单元修后实际读回为 **ready**。该次不是父级 LLM 自动请求：本轮尚未证明默认自主选择 review_units 或任意多层递归。父级字段选择／整体整合与 Host 确定性执行分别保留。
6. 新独立只读 GLM 读取原文、实际 revision 3、冻结四题及 local-history 阶段产物（含原始治理读取），**4/4 PASS**，`local-rework-20261030-start1/evaluations/local-rework-check/`。原故障、原 revise、自查及应用均保留。

### collaboration/routing：检查材料发布后父级不可读

- 随后用真实父级工具身份检查，发现 `check_material_ref` 已生成，但原 helper 没有向父级交接，`TeamChannel.read` 正确拒绝 `handoff_material_forbidden`。这不是模型质量失败，不能因为局部检查 ready 就忽略父级无法取证。
- 两项新增用例在正常／已 handoff 父级下均先失败。最小修复沿既有材料与 TaskControl 通道：Host 将检查结果及原始治理读取冻结为精确版本材料，并向原直接父级登记带材料引用的结果消息；消息登记不绕过原调度、控制和预算；已 handoff 的父级未因此新开 LLM 回合。通用 Agent 的 closed-task 发送规则和材料读取权限均未放宽。
- `governed_read_material_ref` 供父级按范围读取原始响应，不把长上下文塞进证明正文。缓存复用不重复发送；新版本另留证明。相关 **42 passed**，包含父级实际读取与无重复消息检查。
- 新代码下 A 原单元实际检查 ready，生成两份可读材料；对旧代码已经完成的 B，只补一次明确 Host 技术转交和原始读取材料，不改旧证明／旧事件，也没有再次让 GLM 修模型。
- 通过与 read_handoff_material 相同的父级 `TeamChannel.read` 实际读回 A／B 的证明及 query_semantic_context、read_model_resource 原始响应，均绑定 revision 3；回执 `parent-proof-read-receipt.json`、修前 `parent-check-read-before.log`、修后 `parent-proof-read-after.log`。这是 Host 以父级身份执行的确定性权限／可读性核对，不宣称另有父级 LLM 消费回合或新独立语义报告。
- 先前四题独立评价覆盖实际模型和局部修订轨迹；这次后继交接修复另由失败复现、相关回归及真实工具读取证明，没有拿旧 4/4 覆盖新增运行代码。

### 本批最终结论和保留风险

- 最终完整 v5 回归 **194 passed、1 条既有第三方 warning、159.05 秒**，`local-rework-20261030-inputs/final-regression.log`；覆盖后继 CLI 反馈、原单元自查和材料交接代码。Ruff、diff、文档链接检查覆盖最终差异。
- 第三项账本最终估算 **0.29092860 CNY**，14 个已知计量单元，无暂估、inflight=0，计量覆盖 complete，剩余 **2.70907140**。三项任务均未耗尽或追加预算；外部 Host／未接线辅助调用仍单列 unknown，不以零费用冒充完整成本或最终账单。
- 第三项已 stop／cleanup，九个本批自有运行均停稳，临时凭据撤销；非空模型与失败证据保留。第三项回执 `followup-20261030-inputs/cleanup-local-rework-20261030-start1.json` 同样确认 aggregate_keys_non_active 和 no_in_flight_attempts。
- **T01 默认采用仍为 PARTIAL**：新任务导出发现 B 修后记录 body 已说明完整正确、无需变化，states 却 expression=partial；旧“present_but_wrong／needs_expression”记录未明确历史化，父级 coverage 仍引用旧模型 revision，freshness=needs_review。实际模型 4/4 不等于工作空间准确闭合。证据 `local-rework-20261030-inputs/workspace-final-summary.log` 及 `followup-20261030-inputs/local-rework-20261030-start1-records.json`。没有再次由 Host 逐条闭合后把它称为默认成功，也没有增加平台语义完成硬门。
- 下一步优先验证让 Agent 在自查时准确定位已有记录、沿稳定 ID 刷新当前状态及实际依据的最短方法路径；然后继续 T04.2 的跨单元合计／范围受限共同澄清／边界和 T05.2 变化后消费。T03 的任意多层递归、父级自主消费方式、复杂组合及净成本继续保留未验证；完整 v5 方法一致性仍 PARTIAL。

## 推进轮次 D5：让默认自查定位并维护已有记录

- 本轮用户继续授权，沿每项任务 3 元，不追加旧账本或重用旧 PASS。代码起点 `572bd7b`，调查见[默认闭合缺口](../../research/2026-10-30-v5-workspace-closure-investigation.md)。
- 定位：导航不显示 states／model_basis，缺本单元 project 记录；自查提示不直接提供已有记录导航。补充这些已存事实和有界导航，GLM 保留状态判断权；程序没有自动完成、语义硬门或新检索服务。
- 两项缺失导航测试先失败，相关三模块 **43 passed**；完整回归与真实采用继续运行。新增用例同时核对程序不会因提供导航而把 partial 改为 complete。
- 新 task_ref `v5-workspace-closure-20261030`，run `workspace-closure-20261030-start1`，账本 `workspaces/v5-runs/workspace-closure-20261030-inputs/budget`，金额 3 CNY；沿 GLM Flash／low 和两个独立 Class 的公开工程原始材料。生产前冻结六题 `v5-default-workspace-closure-public-20261030`。
- 首次真实 semantic start 约 04:27 UTC，在本轮授权后约五分钟内；未前置完整回归或全面审计。生产不接收具体待改记录 ID，不由 Host 修改 states 或正文。后继受控故障只改自有工程模型，原文不变，仍由原 GLM 单元判断与修订。
- 本轮尚未有独立闭合结论，不能把 43 项开发检查或导航增加当作状态维护语义 PASS。后续结果在本节追加。

- 进一步从旧原件定位作者／单元标签不一致：B 的旧故障记录 unit_id=root，A 的旧自查记录 unit_id=概念 ID。导航现在包含本单元署名记录及分配记录；普通按 unit_id 查找语义不变。两项归属用例先失败后通过。
- 补公开搜索的 include_authored 可选参数，确保本单元有界导航的 next_offset 可用同一条件续页；十一条署名记录的真实 MCP 分页用例先失败后通过。相关范围 **25 passed**，保留普通精确过滤断言。早先 197 项完整回归不覆盖之后的分页差异，最终完整回归另留日志。

### D5 真实结果、故障接续与最终证据

- 初建首次根级提案即完成应用（round 0、实际 revision 1），没有重现上轮把 Class 业务提案当 unified graph 的格式问题。根级沿 `v5-closure-two-classes-coverage` 原 ID 从 revision 1 更新为 2，补实际表达及已审阅／表达状态；`workspace-initial.json` 保存故障前原件。这是当前场景的实际采用，不用不同条件的 round 数宣称净降耗。
- 约定的 Host 受控故障只把 B 的否定改成相反断言，模型 revision 1→2。原 B 实际读取后 revise，原 B／根级 generation 1、A 保持 generation 0；同一 run 修订原 B 到模型 revision 3，A 定义逐字段不变、实际仍只有两个资源 IRI。Host 没有提供待改语义记录 ID 或修改状态。
- 两个原单元修后自查均 ready。A 沿 `equipment-a-scope-propositions` 更新到 revision 2；B 沿 `vr-b-class-meaning` 更新到 revision 3；根级覆盖为 revision 3。三份当前记录均 expressed/current，根级 model_basis 为实际 revision 3。旧 `verification-record-negation-fix` 从 revision 1 更新到 2 并明确 superseded，不再作当前未解决项；历史版本保留。详见 `workspace-final.json`、冻结 `independent-materials/local-history.json`。
- 独立只读 GLM 在生产前冻结的原六题上 **6/6 PASS**，`workspace-closure-20261030-start1/evaluations/default-workspace-closure-check/`，freeze_id=`v5-default-workspace-closure-public-20261030`，实际本体 `4f93b7cb-5750-41d9-9fa6-6669cd877329`、revision 3。独立侧实际读原始材料、阶段原件／历史记录和治理模型，没有修生产或改保留证据。
- 该 run 的业务记录均选择 task 范围；project 范围没有相关记录，不强制复制一套。project_local 的作者／分配归属、精确过滤及隔离由开发用例验证；不能将本次 6/6 外推成真实共享项目记录、跨 run 或所有业务范围均已稳定闭合。Host 仍显式安排原单元检查，未宣称父级全自主选择与调度已经验收。

### runtime/infrastructure：流断开及计量暂停

- B 修后首次检查原生终态 failed，消息为 stream disconnected／上游“网络错误”，错误身份保留在原 result.json；不是模型质量失败、不是五小时额度 429，也没有未知 RDF 写入。失败目录 `verification-record--unit-check-77191c94c0098e335dab-000` 保留。
- 发现 `unit_check_needs_correction` 外层丢失内部 runtime/infrastructure 层。新增失败用例先失败，窄修为保留原 layer、native_error 和 execution_ref；相关 **10 passed**，原候选可重试而不重写模型。
- 随后的原身份重试被账本正确拦下：不是 3 元耗尽，而是 HTTP 200 的错误响应没有用量，触发 metering_error。T0 复核：计量保护真实额度边界，缺用量不能当零；不删除或放宽这个保护。已有 Host `record_attempt_estimate`／`continue_authorized` 已覆盖有证据的暂估和恢复，无需修改预算框架。
- 依据本任务两份完整同类自查的原生回执，对失败的**单次请求**采用“完整同类回合最大输入／输出的 2 倍、输入均按未缓存”的显式暂估，**不是实际用量或数学上界**；`metering-estimate-evidence.json` 保留原请求、两份原回执 SHA256、数值和依据。原始错误响应／空用量未改，后续真实用量若到达仍由既有账本优先处理。
- 通过现有接口登记 **0.182942 CNY** 暂估后，只在计量恢复条件满足时清除 metering_error；3 元授权不变，没有追加、补零或换 run／账本。最终在同一候选、模型 revision、原单元的 `...-001` 回合完成 ready。保留原失败、被拒的重试及恢复回执；不据此宣布“无终态未知原生执行”的 T03.1 已通过。

### D5 开发、费用与收尾

- 最终完整 v5 回归 **199 passed、1 条既有第三方 warning、178.10 秒**，`workspace-closure-20261030-inputs/regression-final-with-failure-layer.log`。此前 197／198 对应阶段差异，原日志保留；最终代码由 199 覆盖。Ruff／diff／链接检查按最终差异执行；不改 backend／frontend／共享依赖，不需要应用服务重启。
- 当前任务最终估算 **0.51603408 CNY**，其中已计价 **0.33309208**、失败请求暂估 **0.182942**；剩余 **2.48396592**，12 个账本单元、1 项暂估、inflight=0。覆盖为 PARTIAL，不能写成最终账单或完整净成本。外部 Host／未接线辅助调用仍单列 unknown、不扣任务金额。`budget-final.json`、全部失败及恢复事件保留。
- 本轮最初真实 start 约 04:27 UTC，首次交付约 04:31，局部修模约 04:33—04:36，断流后的计量定位／恢复约 04:37—04:41，后继自查约 04:41—04:42，独立评价约 04:42—04:46。区间含并发／等待，不相加冒充精确有效时间；未单独计时的 Host 有效工时不补造百分比。技术故障后沿既有暂估恢复接口走短路径，没有扩建 harness。净降耗仍缺同条件对照。
- 运行已停稳并清理临时凭据，保留非空工程模型和全部证据。清理回执 `followup-20261030-inputs/cleanup-workspace-closure-20261030-start1.json`，已确认 aggregate_keys_non_active=true、no_in_flight_attempts=true。
- **范围结论**：T01 的本轮默认自查复现问题已在有界新任务中自行闭合，未经过 Host 逐条修记录。T01 完整低频例外／父级未分配范围／未审阅情境仍待 T04.2 联验；T03 自主递归、T05.2 消费、T06 同条件降耗等不因此关闭，完整 v5 方法仍 PARTIAL。下一步按原计划进入 T04.2／T05.2 的真实组合、遗漏与范围变化验证。

## 推进轮次 D6：组合规则、父级剩余范围与限定澄清

- 用户同意继续，沿每项任务 3 元；本轮仅一个稳定账本 `composite-contracts-20261030-inputs/budget`，覆盖初建、澄清、后续来源变化、自查、失败与独立评价，不重置额度。
- 范围与来源选择见[组合范围调查](../../research/2026-10-30-v5-composite-scope-verification.md)；静态[参考场景](../../evaluation-scenarios/v5-composite-contracts/README.md)不是工业客户业务真值，也不使用 Schema 推断未确认政策。
- `v5-composite-contracts-20261030`／`composite-contracts-20261030-start1`，沿 GLM Flash／low、四个责任单元、十个逻辑引用；十二题 `v5-composite-contracts-twelve-public-20261030` 在生产前冻结。未来额度文件和固定补充不进入初始生产材料包，只经真实输入／来源修订投入。
- 约 05:59 UTC 已开始首次真实建模，在本轮授权后约九分钟内；没有前置新全回归。当前运行代码为 `f647d50`，相关环境未变，复用 199 项开发回归。初期正在形成局部结果与真实年度问题，独立语义和后继变化尚未执行。
- 本轮需区分：公开组合场景的正例、已捕获未表达负情境、限定范围答复、来源变化后消费及 L2 重复性。某个部分通过不关闭其余条件；来源撤回、跨 run 项目记忆与净降耗保持待验证。

### D6 已保留的限定澄清与生产阶段

- 四个责任单元为 contract-year／installation／repair／parts，只有年度单元提出一个真实共同请求 `human-request-4b6c261ba07fd32d8b8602b0`。十个引用是材料中的逻辑范围，不是十个实例或十个独立执行单元，不能据此宣称任意规模并行。
- 首份署名补充 `composite-year-partial` 只确认甲类。约 06:06 UTC 的实际状态为 answer_consumed、共同问题未解决、年度单元 waiting_input；其余三个单元已有 proposal，根级安全部分应用后等待。原观察 `status-before-answer.json`／`partial-snapshot-receipt.json` 及 `alpha-partial-beta-pending` 快照保留；没有把排队、投递或消费当作业务范围全部解决。
- 第二份 `composite-year-complete` 沿同一请求补齐乙类，两个消息都已消费，共同请求才变为 resolved。实际模型 revision 2 有七个 Class，包含共享额度、三类局部含义、甲乙各自年度及父级正式完成／临时许可。原始补充明确署名 test-scenario-owner，不作为客户亲自确认。
- Host 显式安排四个原单元实际读回，均为 ready，但局部报告保留结构化金额属性未应用、其他单元来源不可自行确认、父级整体条件不在局部责任内等限制。此为生产自查，不能相加充当独立整体验收。
- 根级在交接这些证明后重新审阅，曾因新原生回合未实际读声明的全部来源触发 source_read_missing；同 run 补读纠正，未放宽来源校验。后继识别三条占用到共享额度的关系尚未实际应用，沿真实已应用资源身份补交；不能用卡片或先前提交声明代替应用回执。代码仍未修改，这类补读／重复整合成本保留给 T06 分析。

### D6 初始评价与后继结构缺陷

- `composite-v1-check` 在 revision 3 得到初始九项 **9/9 PASS**，freeze 为原十二题的适用子集（1—8、12），原主冻结未变；实际读取原文、human-inputs、phase-history 的相关头段及十个资源。该结果是公开参考场景的独立语义报告，不是未来版本、负对照或 L2 的证明。
- Host 随后逐字段检查真实 relation-type-list，发现三条关系 source／target 双重编码，未指向原 Class。原报告没有核对这项实际拓扑，**不将原 9/9 升级为整体结构正确或完整 L1 PASS**。原 report／原模型快照与回执保留，不改分数掩盖缺陷。
- 已定位 platform-contract：Host read_binding 误把治理投影 id=IRI 当原生 ID；原生关系写入字段需要原生执行 ID。T0 与影响检查见上述研究；新增两个真实投影用例先失败，修后本模块 13 passed。独立侧补实际关系端点提示（单独保留 prompt-contract 漏查），四个既有参数用例先失败后修订；完整回归进行中。
- source-revise 已投入 quota-v2-120000（同一账本）。原计划只复核三个金额单元，实际记录显示年度单元旧笔记也含 100000，因此显式纳入四个原单元和两份已知受影响年度记录；年度定义本身不改。旧版本／旧报告保留，来源周期创建新原生上下文，不加载全部旧聊天。
- 变更期间自然暂停，无在途后向原根级发送署名 Host 技术反馈，只说明端点身份错误、已修 Host 及实际读取／修复要求，不写业务答案。恢复原 run／原来源周期，由 GLM 复核并修原关系与额度；未在另一个模型中覆盖现场，未追加预算。

### D6 受控父级遗漏与补读反馈

- `composite-contracts-20261030-parent-omission` 为自有隔离 fixture；task_ref／budget_ref 与原任务相同，没有新 3 元或生产 semantic start。Host 只从已应用父级表达复制并删去业务含义中的低频许可段，写入前冻结原题 4 的一题子范围；没有生产自查／建模流程 PASS 声明。旧完整命题作为捕获工件保留且要求独立读取，不能补当前图。
- 新独立只读评价 `parent-omission-check` 得到 **0/1、REVISE**，正确指出当前模型缺许可表达。原 not_applicable 尚保留部分否定限定，报告将三个限定均称缺失的理由过宽；只采信可核对的许可主句遗漏与拒绝方向，不把所有理由当成已证事实。该结果也不替代生产闭环或 L2。
- 来源周期又复现根级 model-00005／repair--model-00001 只读新 quota，却声明全部四份 source_refs；现有错误未列缺项，造成重复纠正。补提示明确本回合读取的声明口径，并让 source_read_missing 带 material_ids；既有历史引用仍保留，不强制每回合读全部材料，也不自动补证。新用例先失败，相关 **20 passed**，最终回归进行中。
- 账本约 2.30 元时暂停新推进，待现有回合自然结束后恢复已准备好的应用／原单元工作；约 1.15 元为既有账本自动 native_transport_deficit_peer_2x_not_upper_bound 暂估，不是已收到的提供商用量或数学上界。预算未追加、未清零或下调暂估。本任务到 3 元后按用户要求暂停，不用未知或失败零费用延长调用。

### D6 修后实际身份与剩余局部偏差

- 最终代码全 v5 回归 **202 passed、1 条既有第三方 warning、162.96 秒**，`composite-contracts-20261030-inputs/regression-final.log`；此前 201 对应尚未补读反馈差异。Ruff／diff 检查通过；未改 backend／frontend／共享依赖，无应用服务重启。
- 根级沿原资源应用四项修订，模型 revision 3→4：共享额度与三条关系文本使用 120000，关系改用真实回执身份。Host 从原 Agent apply-00004 的引用意图逐一对账，三条关系全部六个实际 source／target 与原预期 IRI 相等；十个原资源的 native ID／IRI／Ontology 均保留。原件 `relation-identity-reconciliation.json`；这是确定性的引用执行完整性，不是业务语义评分。
- 根级生产自查在 revision 4 **自行发现**返修 business_meaning／not_applicable 和安装 applicability 仍将 100000 当本版本上限，登记准确缺口并准备原 Class 局部更新；未把共享类及关系已更新当成全模型已完成。该修订与后继独立十二题结果仍待运行，不能提前判 T05.2 PASS。
- 隔离父级遗漏 fixture 的评价已结束，已 stop／cleanup，临时凭据撤销、非空模型及原 REVISE 保留。回执 `followup-20261030-inputs/cleanup-composite-contracts-20261030-parent-omission.json`；原生产 run 仍在同账本推进，不在此清理声明内。

### D6 最终冻结评价的首个原生报告被拒

- 模型已到 revision 5，四原单元 proposal_ready、根级 handoff_ready；修后来源声明不再重复触发缺项。只读实际模型加原生编译器另外实测 model-read 适配路径：真实治理投影 id=IRI，修后六个 source_class_id／target_class_id 均等于实际回执 native ID，未应用新写入。保存于 `corrected-model-read-runtime-proof.json`；使用独立验证输出目录，没有覆盖原坏 verified-reads。
- `composite-final-twelve-check` 首回合自报 12/12，却未直接读取全部必需 workspace 工件，原守卫拒绝 evaluation_report_needs_correction / evaluation_human_source_not_read，detail.material_id=v1-workspace-1。**不是有效 12/12，不发布为整体通过**；原结果保留于 `evaluation-d2af0a74a84b6cb214c5-000`，report-attempt 保留。
- 同一原生报告把多份变更引用称为十三个原始资源，实际十个不同 IRI。进一步明确独立提示须逐项读每份必需工件、按不同 IRI 计数；现有四参数用例先失败，最终回归另留 `regression-final-with-required-artifacts.log`。原目标、原十二题 SHA256、原 package 和全部 required-artifact 不改，沿同一评价 ID 开新只读上下文修正取证／报告。
- 新增总览消费三题是在模型 revision 5 交接之后、对应总览生成之前冻结，与原十二题分别记录；主评价未完成前不生成该总览。来源撤回、生成中变化及 L2 重复性仍未发生。

### D6 同冻结十二题有效通过

- 保留首回合拒绝后，同一评价 ID 的 `...-001` 新只读上下文实际读完全部 **23** 份必需工件、四份原始资料、署名补充及实际模型，得到 **12/12 PASS**，freeze_id=`v5-composite-contracts-twelve-public-20261030`，实际本体 `150e6fc3-25c5-4580-a82c-accc0a931194`、revision **5**。原 package／主标准 SHA256 均未改。
- 本范围覆盖旧／新共享上限及包含边界、局部均成立而合计不成立、父级正式完成／低频许可、限定甲类 partial 与乙类未决、完整共同确认、原模型／认知与资源身份复用。与隔离遗漏反例结合，支持本公开参考范围的 L1；不是客户业务盲测、任意规模或 L2。主评价没有对受控遗漏 fixture 判 PASS。
- 报告仍有“8 个不同资源”的计数措辞，而实际为十个不同资源 IRI（七类三关系），不是按读调用数或变更 alias 数推导。真实资源总量及六端点身份以 Host 原始治理读回／意图对账为准，不照收这项报告数字。R2 的漏查与过宽叙述风险因此继续保留，不能只凭总分作完整性担保。
- 最终提示修正后的完整 v5 回归仍为 **202 passed、1 条既有第三方 warning、175.33 秒**，日志 `regression-final-with-required-artifacts.log`；之前的 202 对应前一提示版本，均保留。最终代码 Ruff／diff 检查通过。
- 截至主评价结束估算 **2.81867860 CNY**，剩余约 **0.18132140**，金额覆盖仍含缺失传输暂估；原标准不改，后续仅在原预算开放时执行已冻结的总览消费子范围。来源撤回、L2 重复性、摘要版本／权限漂移与同条件净降耗未因此完成。

- 影响集证据边界：本次 source-revise 的四个 affected_units 与两条年度 affected_records 由 Host 对照变更前的实际记录显式圈定；不能称为 Agent 自主发现全部影响。根级在 revision 4 自行发现安装／返修残留的事实另有原生自查原件，二者不混同。Host 也显式安排过四个原单元检查／父级重入，尚不证明全自主递归调度。

### D6 当前总览消费与最终收尾

- `overview-refresh` 用独立只读上下文，仅挂载实际目标，生成 consumer 导航；实际记录 `overview-current.json` 为 current、model_basis revision 5。摘要保留当前与历史额度、甲乙年度、正式／临时模态、额度不豁免及真实未知，并披露排序降级／未展开范围；精确决策仍需下钻实际定义。
- 新独立 `composite-overview-check` 在追加冻结三题上 **3/3 PASS**，scope_id=`composite-current-overview-consumption`，freeze_id=`v5-composite-overview-three-public-20261030`，目标仍 revision 5。实际读取四份原始材料、human-inputs、总览、原生输入／工具轨迹和实际定义；没有用摘要填模型缺失事实。原主十二题报告未覆盖或更换，不把两个分母合并成新盲测分数。
- 最终 task 账本估算 **2.87424676 CNY / 3 CNY**，其中已计价 **1.72668676**、既有缺测暂估 **1.14756**；余额 **0.12575324**，37 个计量单元、1 项暂估、inflight=0，覆盖仍为 **PARTIAL**。没有追加或重置，也不为耗尽余额额外调用。外部 Host 和未接线辅助消耗单列 unknown，不扣任务金额，不以估算代替提供商最终账单。原件 `budget-final.json`／budget/state.json。
- **已知原生 Token**：建模侧（含局部／根级自查、格式纠正与导航）输入 **5,233,435**、输出 **114,985**；独立评价（含被拒回合、负对照、后继重试及总览验收）输入 **916,354**、输出 **15,482**。合计输入 **6,149,789**、输出 **130,467**、输入加输出 **6,280,256**；其中缓存输入 **5,045,888** 已包含在输入内，不重复相加。36 个原生统计段均有 fresh-zero baseline，按段取累计末值；缺测传输费用的暂估不提供精确 Token，Host 未计，不能称全账户最终用量。
- **执行时间**：首个原生语义执行 **05:59:12 UTC**，最后原生结束 **07:09:37 UTC**，窗口 **70 分 24 秒**；到停稳／清理观察 **07:10:19 UTC** 为 **71 分 06 秒**。前置准备约九分钟另计（早于首次 start，没有精确 Host 有效工时计时）。原生生产建模区间 union **20 分 20 秒**、生产自查 **11 分 05 秒**、独立评价 **6 分 39 秒**、导航生成 **55 秒**；分类可重叠，全部原生区间 union **37 分 46 秒**，含模型／服务等待和工具，不能当纯有效语义工时或将分类相加冒充墙钟。统计原件 `observed-usage-summary.json`。
- 生产建模＋自查的可观察原生区间 union 约 **30 分 26 秒／70 分 24 秒**，低于窗口一半；有效 Host 排查／文档时间 unknown。已发生来源声明补读、格式纠正、父级复审及评价重试，不能以缓存或较低 GLM 单价掩盖其 token／时间。按 AGENTS 的优先级，后续**暂停扩展平台／harness，先用既有路径缩短真实往返和同条件复跑**；本批只修直接保护引用、来源和取证的窄失败，没有新增业务裁判或运行框架。
- 最终完整快照 `composite-final-v2-accepted`：snapshot_id=`1ca7fce909fc49f79748ff9ab7f4ce5b`，包含工作流、项目记录及真实 platform-data，捕获管理员密钥已撤销，model_read_error=null。原部分答复快照和全部坏端点／失败／被拒报告保持。
- 两个自有运行均 stop／cleanup：原生产 `composite-contracts-20261030-start1` 与隔离遗漏 `...-parent-omission`。回执均 **aggregate_keys_non_active=true、no_in_flight_attempts=true、written-retained**；临时平台凭据撤销，非空工程模型与证据保留。无后续后台建模／监控安排。回执见 `followup-20261030-inputs/cleanup-composite-contracts-20261030-start1.json` 及对应 omission 文件。
- **收口范围**：本公开参考任务的组合、父级条件、限定共同澄清、金额／年度边界、显式额度变化与当前总览消费已有上述独立结论。完整 v5 仍 PARTIAL：L2 相同标准重复、来源撤回、旧总览失效／权限与生成中变化、跨 run 项目记忆、自主完整影响发现及同条件净降耗尚未因此完成。R2 的实际漏查与理由精度问题仍跟踪，不用当前总分删除旧失败。

## 推进轮次 D7：原单元局部闭环与三层责任

- 用户继续授权补齐方法差距；本轮首个目标为 R5.0-003／004、T03 的原责任读回和局部纠正，设计／影响边界见[局部闭环接线](../../research/2026-10-30-v5-local-closure-ownership.md)。不新增多写者或平台业务裁判。
- 可选 review_units 从模型提案传递：应用／no_change 后，先由原单元读回，再做父级整体自查；嵌套声明复用同一 helper，自下而上检查。非 ready 重开原单元与祖先，未变兄弟复用；没有声明仍走既有路径，不把角色数量／所有子级检查变硬门。
- Task `v5-local-owner-closure-20261030`，run `local-owner-closure-20261030-start1`，稳定账本 `local-owner-closure-20261030-inputs/budget`，3 CNY，全部托管角色 GLM Flash／low。复用组合场景并在起点提供已署名年度补充，避免重复已验访谈；这是公开 Host 参考资料，非客户确认。新六项标准在初次生产前冻结，见[参考范围](../../evaluation-scenarios/v5-local-owner-closure/README.md)。
- 约 07:54 UTC 已实际启动原生 parts／repair，距本轮授权约十分钟；当前树是根级整体／parent-scope、expenses 组合中间层及其三类叶子，contract-year 是根级另一个子单元。工作责任层不成为业务类或 Ontology 数量要求。
- 四项机制用例与原检查相关范围 14 passed；证明阶段路由与活动单元调度修改后两模块 20 passed；来源 SHA 反馈两用例先失败，相关 29 passed；旧固定 peer 名单拒绝反例先失败，flow＋team 33 passed。初版 206 项全回归不覆盖后继接线差异，最终回归另记，不拿旧结果作新代码 PASS。
- 真实早期保留 repair 来源摘要误抄与 expenses 的 team_not_configured：前者补可定位期望／收到值，后者按 T0 删除不必要的静态 roster 拒绝。两次自然暂停只为加载窄修复，原生结果、候选、账本与原目标保留。没有 unknown 模型写入，也没有 Host 单独 check-unit／重开指定叶子；真实自动闭环和独立结果尚待取证。

### D7 三层真实运行暴露的交接时序

- 根级先安全应用年度和父级命题四类，声明 contract-year 检查，程序已自动由原年度单元实际读回。expenses 在根级该次自查期间恢复并交来三类金额／共享额度提案；原自查 ready 只覆盖安全部分且 issues 明示费用未表达，但原调度在子级均 proposal_ready 后误交接。
- 未发布该 handoff 为完整语义 PASS。保存 `premature-handoff-evidence.json` 的原 work、自查引用和未处理新消息；新输入反例先失败，修后模型回合实际收到消息、no_change 路径未重复 apply。修复在自查结束和 finalize 前后投递新到 model 输入，不按数量或正文程序判语义完成。
- Host 为已经误交接的历史状态仅做一次根级技术重入，未选择叶子、未改单元状态或语义内容；此为开发期加载修复的明确干预，不称冷启动全自主成功。随后原根级消费 expenses 并应用，已自动进入安装／返修等原叶子检查，中间／根级整体结论仍待取证。
- 首次后继完整回归 210 passed／2 failed；两条检查测试的 fake parent 没确认已投递的旧子结果，在新消息处理条件下持续回流。测试模拟改为仅确认其实际 Queued IDs，保留所有真实检查／顺序断言，不删除业务或流程验证。最终回归与真实证据另记，不用前一结果称 PASS。


### D7 自然局部纠错与最终开发回归

- 根级实际模型 revision 2 后，原 repair 读回自行发现参与共享额度关系尚未表达，返回 revise；WorkPlan 自动重开 repair 和 expenses／根级，parts／installation／contract-year 代次仍 0。原 repair 通过真实回执引用补提关系，Host 未选叶子、未代写语义。
- revision 3 三关系已应用，expenses 自查发现共享额度还留着“关系待补全”旧未知；自动仅重开 expenses 及根级。费用单元提供原 Class fields-only 修订，原资源和真实未知保留。原错 JSON／技术反馈与全部局部结果保持，不以新成功覆盖。
- 当前代码完整 v5 回归 **214 passed、1 条既有第三方 warning、172.84 秒**，`regression-with-nested-overview-final.log`；相较此前 212，新增两参数分层总览用例。Ruff／diff 检查通过。没有修改 backend／frontend，不触发服务重启；真实整体／受控反例和独立语义评价尚待完成。
- 分层导航补齐范围见[研究说明](../../research/2026-10-30-v5-hierarchical-navigation.md)：sections 支持可选多层 children，共享 IRI 可多专题引用，叶子同样核对真实读取；原扁平输出兼容。附加导航三题已在生成前冻结，与主六题分开；仍用 D7 同一 3 CNY，不新建账本重置成本。候选／工作／允许验收结论的多截止点用户投影未因此实现。


### D7 受控反例与真实交接差距

- 初始 settled 模型 revision 4，八类／三关系，`initial-stage.json`；Host 控制只改返修 business_meaning 为错误独立额度，实际 revision 5，`fault-stage.json`。只有一次整体根级重查，无 Host 指定叶子。root model-00004 自行发现，再由 Agent reopen repair；repair model-00005 实读后确认矛盾并提原资源修订。检测首先来自根级，不称叶子 unit-check 在故障版本先返回 revise。
- 中间 expenses 重入 no_change 未转交 repair 的新修订／精确引用且未重新声明叶子检查；root model-00006 遇 handoff_material_forbidden 后从原 owner work issues、原文和实际模型重建意图。原根级“bottom-up through expenses→repair”声明不代表检查真正执行；以实际证明为准。权威提示已持久修正有界转交和检查选择，旧冻结运行不冒充修后提示已验证。详细原件见[局部闭环说明](../../research/2026-10-30-v5-local-closure-ownership.md)。
- expenses 实际检查期间上游回执迟到触发 metering_error；自然停稳后原生累计记录已覆盖该 source 的十个 completed attempts，所有 current_issues 为空。沿既有 tick／continue_authorized 的恢复校验，只清 recovered metering_error，原 3 CNY、已有 0.22660 暂估及原始回执不改。`metering-reconciled-evidence.json`／`budget-after-metering-recovery.json`；没有追加金额、把未知记零或放宽守卫。


### D7 原始六题报告的证据错配与导航结果

- `original-owner-six-check` 在 revision 6 原生返回 6/6 PASS，且格式／必需工件读取守卫通过；但第 4 项称“故障后 repair unit check drove revise”，第 5 项称“最终 repair／expenses／root 检查相容”，实际 repair 单独检查证明只有 revision 2／3，外部故障在 5，修后在 6。原故障是 root model-00004 先发现、repair model-00005 实读提修订，不等于 fault revision 5 的 self_check 返回 revise。故**该总分不作为完整流程 PASS 采信**；原 private-report／public-feedback 不改写。
- 第 6 项还披露用 category Class IRI 作为 relation-type-list.entity，返回 0，却未沿已知 relation IRI 查实际端点。Host 原治理原件在 relation IRI 下确有 source／target。这属于取证／解释精度问题，不能以“存在关系”代替拓扑已验。
- 独立提示持久补同 incident 的 unit／generation／revision／native purpose／确切证明与时间线核对，以及 relation-type-list 使用 relation IRI。四参数合同用例先失败；修后 acceptance 模块 **17 passed**。没有新增平台语义裁判或自动改分，原六题和 package 不改，使用全新只读评价 ID `original-owner-six-evidence-recheck` 复核，仍扣原账本。
- `local-owner-hierarchy` 从实际 revision 6 生成 current 导航，13 个主题条目、sections 最大嵌套 2 层（另有整体 summary），8 个 IRI 跨主题重复引用。`hierarchical-overview-three-check` 在生成前冻结的附加三题上独立 **3/3 PASS**，目标仍 revision 6；只读原生输入／工具原件和实际模型，主六题分母不变。旧摘要失效与后继模型版本另验，不把当前三题推广为完整 C2。
- 最终生产提示新增精确交接规则后的相关合同／通信／总览 **30 passed**；前一完整开发回归 214 项仍覆盖全部运行逻辑，后续只调独立提示的 acceptance 17 项另验。当前未改后端／前端，无服务重启。


- `original-owner-six-evidence-recheck` 首个新上下文又自报 PASS，但未读 frozen-questions，将原流程六题换成其自定的六项模型内容检查；现有守卫以 evaluation_frozen_source_not_read 拒绝，未发布为有效评价。补权威提示明确直接读取 frozen-questions、原编号／范围不可替换；保留该 `...-000` 原结果，沿同一评价 ID 的新只读 `...-001` 继续，原冻结和预算不变。这再次说明独立角色标签／格式守卫不能代替实际取证质量。


- 同一复核 ID 的 `...-001` 已读冻结题后仍返回 6/6，但把 Host 留存的 fault-retained-read 归为 original-owner read，并称存在 repair revision 6 check；原件只有 revision 2／3，该解释不成立，**不采信为完整闭环 PASS**。取证包压缩时省略了该历史读取的 Host 观察者标签，是本次包装的明确缺陷；原始 stage 的 Host-collected 标记仍保留。后继包将明示 observer／native execution，并单列实际当前 proof 的 basis／generation；不改原坏报告、不再以相同不明确包无差别重试。验收提示补 Host 观察与原 Agent 读取不可混同，R2 仍保留。


### D7 同预算第二阶段：修后交接采用

- 不重建任务、不追加金额：stage2 仍为 `v5-local-owner-closure-20261030-start1`／原 3 CNY；原六题 SHA256 不变，首轮误判及坏流程证据保留。当前 baseline 是 revision 6，第二次仅将同一自有返修定义改为同样外部矛盾，revision 7；原生生产不知道隐藏题或旧私有评价理由。
- 只向根级发一个整体检查请求，附通用、已持久落盘的方法合同澄清，未指定叶子或提供业务修订；本有界实验明确先用 no_change＋当前中间声明安排原责任检查，再由真实失败触发原身份修订。这是实验选择，不是所有建模的新增强制阶段。
- Host 第一次投递被 human_input_task_closed 拒绝，无输入／模型写入；随后经既有 WorkPlan root reopen 一次并 initialize，再接受同一稳定 ID 的整体技术输入。原拒绝保留，没有手工改单元或清空 active。
- 真实 revision 7 下 `overview-show` 已将 revision 6 导航返回 **needs_review**，保留原 body／model_basis，没有冒称当前；`method-repair-stage2/old-overview-after-external-change.json`。这是本模型变化的实际版本失效证据，不替代来源撤回／权限漂移验证。
- 第二阶段验收包明示 Host 历史观察并非原 Agent 读取，保留原生目的／执行引用，并列原工作代次与实际检查 basis；只导出原字段，不新增语义评分器或自动判题。最终结果待实际运行，不先计 PASS。


- 第二阶段已实际发生原故障版本检查：root model-00007 返回 no_change／review_units=[expenses]，expenses model-00007 返回相关提案／review_units=[repair]；程序在未修图的 revision **7** 调起 repair `unit-check-57c407...`。原生 purpose=self_check、actual basis=7、result=**revise**，明确定位错误独立额度；WorkPlan 自动将 repair 2→3、expenses 3→4、根级重入，parts／installation／contract-year 仍 0。`method-repair-stage2/fault-original-unit-check.json` 同时保留原程序证明、原执行意图、原生实际治理读取及当时工作树；Host 仅导出原件，不代判业务语义。后续原修订与最终读回仍在进行。


- 原 repair model-00006 和 expenses model-00008 沿原身份提／转交局部更新，根级将修订应用到 revision **8**；随后 model-00009 实读确认该更新已有效，改回 no_change，不重复提交同一成功变更。原 repair 已在 revision 8 完成新的实际检查，费用中间层按声明继续本层核对；整体最终判断和独立六题仍待完成。


- 最新完整代码回归 **214 passed、1 条既有第三方 warning、168.05 秒**，`regression-final-with-evidence-provenance.log`。其后仅补独立提示 source_ids 的自动 human-inputs 项：四参数用例先失败，acceptance **17 passed**。没有更改冻结源版本／题集或新增判分规则。
- 修后主评价 `original-owner-method-repaired-six-check` 首原生回合已能对应 revision 7 的 57c407 self_check／revise 与 revision 8 的 ec62／34dcebbe 证明，但漏读新 human-inputs 被既有守卫拒绝。原因是自动增加的来源受校验却没有列入提示 source_ids；现显式列入，按同评价 ID 的新只读 `...-001` 重试，仍计原账本。当前分母六题不变，不发布被拒的自报 PASS。
- revision 8 的导航已沿同一 ID 刷新为 current；旧 revision 6 的 needs_review 记录及历史三题 PASS 保持，后继当前导航三题按原附加冻结另验，不混成新的总分或业务盲测。


### D7 修后六题有效结论

- `original-owner-method-repaired-six-check` 的 `...-001` 实际直接读 frozen-questions、五原始材料、human-inputs 与 16 份必需工件，并查询实际 revision **8**，有效 **6/6 PASS**；freeze_id=`v5-original-owner-closure-six-public-20261030`。第 4 项明确区分原 repair `57c407...` 的 native self_check／revise（basis 7）与 Host 留存观察，第 5 项对应原 repair `ec62...` ready、expenses `34dcebbe...` 引用该 child proof 及根级实际目标 8，原错误／拒绝／两个故障版本保持。
- 修后实际采用：有界初始声明＋故障时 no_change 检查路径，在原单元实际读回发现错误，再沿原身份／祖先重入；父级只负责中间结果、共享规则和未分配条件，统一 Host 应用维持。根级曾采用中间层已携带的有效原修订，后继中间层再确认原意向，root model-00009 实读并 no_change，未重复成功应用；不虚称所有执行字段都来自一个新叶子提案或显式转发了所有孙级私有材料。
- 实际资源仍 **11** 个不同 IRI（八类、三关系），native ID／IRI 集合保持；第二阶段只改变返修语义定义，三个无关兄弟代次仍 0。独立报告确认同合同／年度共享合计、包含边界、甲乙年度、父级正式／临时模态和真实未知；这是公开有界 L1，非客户盲测、任意递归／规模或冷启动 L2。
- 本轮采用了署名通用方法合同补充、初始根级技术重入及一次计量恢复；权威提示已持久修复，但不能据同 run 的修后采用宣布无临时补充冷启动通过。R2 的历史误归属／虚构版本证明风险仍保留，不以新总分撤销已确认失败。


### D7 当前导航、成本、时间及收尾

- `hierarchical-overview-current-three-check` 在同一追加冻结三题上，实际 **revision 8 独立 3/3 PASS**；scope_id=`local-owner-hierarchical-overview-current-after-repair`，freeze_id=`v5-local-owner-hierarchical-overview-three-public-20261030`。原 revision 6 的 3/3、模型变成 7 时旧导航 needs_review、修后 8 的 current 与本次新评价分别保留，不合并分母。
- 最终估算 **2.97079536 CNY / 3 CNY**：已计价 **2.36304736**、缺测暂估 **0.607748**，余额 **0.02920464**；59 个计量单元含 5 项既有自动 native transport deficit 暂估，inflight=0，覆盖 **PARTIAL**。没有追加、清账或将未知置零；不为耗尽剩余约三分钱再调用。外部 Host／未接线辅助按约定 unknown／不扣金额，不是提供商最终账单。
- **已知原生 Token**：建模侧（含格式纠正、协作、原单元／根级自查及两次导航）输入 **6,198,217**，输出 **138,025**；独立侧（含误判、被拒及重试、两个版本导航评价）输入 **1,265,411**，输出 **22,522**。合计输入 **7,463,628**、输出 **160,547**、输入加输出 **7,624,175**；缓存输入 **5,859,968** 已包含于输入，不再相加。54 个统计段均有 fresh-zero baseline，按段取累计末值；五项金额暂估没有精确 Token，Host 用量不在此数内。
- **执行耗时**：首原生 **07:54:40 UTC**，最后原生 **09:32:03 UTC**，窗口 **97 分 23 秒**；到清理后 **09:36:53 UTC** 观测为 **102 分 14 秒**。授权后约十分钟进入首真实 start，准备另列；Host 准备／修复／测试／文档有效时间未单独计时，不能把进程存活当语义工时。可观察原生区间：生产建模 union **23 分 27 秒**、生产自查 **22 分 34 秒**、独立评价 **8 分 57 秒**、导航 **2 分 22 秒**；分类可重叠，全部 native union **54 分 12 秒**，包括供应商等待／工具。
- 生产建模＋自查 union **43 分 43 秒／97 分 23 秒（约 44.9%）**，连这一含等待的上界也不足一半。实际已发生来源／格式纠正、根级重复唤醒、中间层漏转修复和多次评价返工；不能以低单价或缓存掩盖累计上下文。按 AGENTS 的既定门，**停止继续扩展平台／harness，下一步先用持久修后提示与有界精确原件走更短的真实验证**。无临时补充冷启动、完整多视图、来源撤回、跨 run 接续和同条件净降耗仍未关闭；不再前置新控制机制。余额不足有意义的同任务复跑，不能靠改名新建同任务账本清零。
- 完整快照 `local-owner-method-final-v8`，snapshot_id=`f9cc9ff3175a4ecfbcc901a521ba3fed`，202 个对象，并有项目记录／真实 platform-data；model_read_error=null，捕获管理员密钥 revoked=true。
- 原生产 run 已 stop／cleanup：**aggregate_keys_non_active=true、no_in_flight_attempts=true、written-retained**，读取、协议和组织管理员临时密钥撤销；非空工程模型与全部原件保留。兼容清理字段 legacy_scope_disposition=failed-written-retained 来自旧 Runner 终态推断，v5 质量／任务结论独立记录（现有 worker 注释已明确），不据它推导语义失败。原件 `snapshot-final-receipt.json`／`cleanup-final.json`／`budget-final.json`／`observed-usage-summary.json` 均在同一 inputs 目录。
- **收口边界**：局部责任接线、修后原身份闭环及多层实际模型导航在本公开参考范围有上述工程／实际采用／独立结果。完整 v5 仍 **PARTIAL**；历史 R2 误归属／虚构检查及漏读始终保留，未证明任意验收均可靠。方法功能、真实采用、L1、L2 与净降耗分别报告。


## 推进轮次 D8：fork 原生身份交接及实际续建

归属 T05.2、R5.0-001 F10／004／007，起点 `5d798e2`。用户同意继续后，将独立目标 `v5-fork-continuation-20261030` 绑定新的稳定 3 CNY 账本 `workspaces/v5-runs/fork-continuation-20261030-inputs/budget`；源建立、fork、显式 v2 来源修订和独立评价同账本，未重置或追加。旧任务账本没有混用。全部原生角色 GLM Flash／low；工程 fixture 与五题在首次生产前冻结，不是客户盲测。

- **复现／修复**：真实源治理读取的 id=IRI、空本地 bindings 的只读编译探针返回 `binding_identity_missing`，没有执行一次失败的真实 fork 或修改该模型。开发红测后，Host 从保存图的显式 ID／唯一类型交接 bindings，并按实际 fork 回执映射目标本体；native ID／IRI 本身保留。ID 不从 IRI 后缀提取；OWL.ObjectProperty 的 relation_type／对象值 property 由已有原生命名空间区分。copied pending 保存身份原件，可在复制完成、本地初始化中断后恢复文件而不重做平台复制；不新增后端 API 或恢复框架。
- **实际运行**：源 `fork-continuation-20261030-source` 初建两个 Class、revision 1，快照 `b85a805235e94b6987a4fcb0cac1d7d0`。目标 `fork-continuation-20261030-target` 为新项目／本体和新原生上下文；显式 v2 材料要求在原设备定义整合编号含义、新增记录→设备关系。GLM 复用两个原类，唯一 `apply-00000`（Batch `f212457d-ef49-4154-9996-036758539b3d`、Attempt `840788ea-4b8d-4c55-bc75-9689472bf031`），目标 1→2，原类身份与关系端点对账正确。
- **实际接续**：候选原生终态后自然暂停在 apply 前，新 CLI 进程从原候选应用、自查 ready。完成 handoff 后另用新进程 resume，原候选／检查结果摘要、唯一操作及模型 revision 2 不变。源再次 capture 为 archived／revision 1、图 10 triples 同构不变。此为已知终态后的接续，不外推缺少 result／turn-completed 或 COMMIT 回应未知的恢复。
- **独立五题**：新只读原生上下文 `evaluations/fork-continuation-five/` 直接读取原材料、原冻结五题及实际 revision 2，并展开关系端点，**5/5 PASS**。Host 导出、自查原生实际读取与独立读取分别署名。报告题 4 的 “at handoff” 概述不精确：其 owner_pid 差异对应 apply 前接续，handoff 后 resume 有另一组原件；不以这句话扩大窗口结论。完整原报告保留。
- **开发检查**：完整 v5 **216 passed、1 条既有 Pydantic warning、189.78 秒**；最终定向 **18 passed**，额外覆盖完整回归收集之后新增的 copied 中断参数分支。Ruff check／format check、diff 和相关链接检查通过。未修改 backend／frontend，不重启应用。GitNexus 对 v5 目标未命中，沿明确调用点、差异、测试及真实平台补证，不声称图谱完整影响覆盖。
- **收尾**：目标最终快照 `06c3d80bfb6a4881b568748297c7161e`；目标 stop／cleanup 确认全部 keys 非活动、无在途 Attempt，保留模型。源原封存回执仍在，3 次源、1 次目标 capture／fork 临时凭据全部 revoked=true。多余重复 source cleanup 返回 `admin key unavailable`，尚未发送撤销请求，没有覆盖原回执；记录为已封存源重复清理的幂等反馈缺口，没有将报错掩盖成成功，也不为此扩建恢复机制。
- **金额与 token**：**0.16588240 / 3 CNY**，余额 **2.83411760**，5 个已知单元、无暂估、无在途，覆盖 complete；非最终提供商账单。建模含自查输入 290,015／输出 7,564／缓存输入 217,920，独立验收输入 306,833／输出 2,373／缓存输入 262,400；合计 606,785 输入＋输出 token，缓存已经包含在输入。外部 Host 单列 unknown、不扣预算。
- **时间／下一步**：生产原生区间 242.54 秒、独立 122.26 秒，首末原生窗口 796.57 秒；含提供商／工具等待，不等于纯语义有效时间，Host 修复／测试／文档有效劳动未独立计时。生产占窗口约 30.4%，加验收约 45.8%；按 AGENTS 停止进一步平台／harness 扩展。先用持久提示和更紧凑、观察者明确的原件验证默认冷启动／取证正反例，净降耗保持未验证。

完整来源、决策、资源身份、费用与未覆盖范围见[交付调研](../../research/2026-10-30-v5-fork-native-binding-delivery.md)。代码／新 fork 有界续建已交付；已 ready 历史 fork 回填、任意外部 RDF 写入身份、原生未知终态恢复、来源撤回、客户盲测、L2 及全方法一致性仍未关闭。


## 推进轮次 D9：中等两业务切片持续迭代（2026-10-31，有界 L1 完成）

用户最高权限与任意使用 GLM 的当次授权覆盖本目标的 usage_only 初建、修模、独立评价和有界重复；同 task_ref=`v5-two-slice-service-20261031`，不改旧账本。四份 Host 工程来源覆盖安装验收／返修履约，原十八题在首次生产前冻结，不是客户真值或业务盲测。

- 首 run 初建因技术合同不完整发生六次未写入编译反馈，后写十二类。原单元／父级把已知未表达部分当作后续范围而 ready，独立 revision 1 **5/18 PARTIAL**。
- 内联候选由 Host 实存并绑定实际引用；补中立候选形状、指标载体字段和 entity／Class 语义层级，完整自查不能把登记缺口当交付。原单元实际读取中的检索排序 429／截断与未核实定位单独保留，不归因语义错误。
- Host 一次错传执行指针作为读定位；查明实际 resource_bindings 后修正模拟形状、原单元导航及当前技术输入，原错误保留。没有新增语义评分器或检索框架。
- 同 run 原身份补交到 revision 2，十八类／十种类级关系，原十八题独立 **18/18 PASS**。这是有界 L1；首轮有技术指导，不是零介入冷启动。
- 第二 run 的旧合同冷启动暴露实例层级问题与额外递归；自然停止、模型保留、所有临时能力封口，无独立范围 PASS。第三 run 冻结持久修复，继续同材料／标准，未输入运行时指导。
- 提交 `47fe7bf`／`55851dd`；最新完整开发回归 **220 passed、1 条既有 warning、184.49 秒**，不是语义验收替代。
- v1 通过后以完整原件保存，再在首 run 激活显式 v2 来源变化，范围是六小时响应目标与临时许可支撑撤回；该阶段及第三轮独立结果、最终总用量后补。

完整输入、失败层、决定、实际原件、未知费用和剩余范围见[本轮推进记录](../../research/2026-10-31-v5-two-slice-service-progression.md)。所有三轮及独立评价统一统计；当前不宣布净降耗、完整方法一致性、客户盲测或 L2 PASS。


### D9 最终补记

- 首 run v2 实际 revision 3 原 v2 十八题独立 **18/18 PASS**，28 个原资源身份全部保持、安装代次 1→1；32 binding keys 含四个 update 别名，实际仍 28 个不同 IRI。四项语义定义发生变化，来源撤回没有被当作原业务事实为假。
- 第三 run 修后默认冷启动实际 revision 2，原 v1 十八题独立 **18/18 PASS**。27 个资源（17 Class、10 relation_type），生产 root／两子级没有 human request／answer 或运行时 Host 补充；原责任在当前版本实际检查通过。自修技术往返保留，不称零错误或 L2。
- 三 run 全部 stop／cleanup，全部临时能力非活动、无在途 Attempt，模型和失败原件保留。旧合同第二轮没有独立完整范围 PASS，未被第三轮成功覆盖。
- 资源封口墙钟 **87 分 06 秒**；首末原生执行窗口 **82 分 37.511 秒**。已知原生输入 **15,103,420**／输出 **366,185**／合计 **15,469,605**，75 线程，含所有失败／纠正／评价。Host 与平台排序用量未知，费用与纯有效语义时间不补零，净降耗未验证。
- 本次交付为两个公开工程业务切片的 L1、所列来源变化及修后默认路径；完整 v5、客户盲测、任意规模、同条件 L2 和记忆／Schema 专项仍按原范围。
