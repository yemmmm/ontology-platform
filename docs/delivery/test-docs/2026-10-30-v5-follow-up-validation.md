# v5 后续任务验证与实施记录

日期：2026-10-30。统一计划：[v5 后续任务清单](../implementation-plans/2026-10-30-v5-next-tasks.md)。
风险依据：[高影响评估](../../research/2026-10-30-v5-high-impact-risk-assessment.md)；
基线核对：[流程一致性](../../research/2026-10-30-v5-modeling-flow-design-alignment.md)。

本文件是后续逐项追加的证据记录，D0 为初始登记，后续实际推进见各轮记录。
原基线 `c9f7171` 的既有证据不改写；本轮实施从 `4e41581` 开始。

## 任务状态

| 任务 | 关联风险 | 验证／定位 | 实施修复 | 真实采用／接续 | 独立语义 | 成本结论 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 状态、覆盖和去向 | R1、R3 | 缺状态／坏依赖／跨 scope 旧覆盖已复现 | 提示、合同和可恢复反馈已修 | 实际采用；有 Host 指导闭合 | 模型 6/6；工作空间先 REVISE 2/3 | 净收益未验证 |
| T02 按依赖分阶段应用 | R4 | 安全部分整层等待已复现 | 最小调度修正已验证 | A 先应用、B 后接续，身份保留 | 公开工程 4/4 PASS | 同条件降耗未验证 |
| T03 子单元闭环 | R4 | 子提案／自查提示冲突及回执歧义已复现 | 有界自查、证明复用及父级接线 | 两个原单元真实治理自查 ready | 不等于独立验收；多层修模待做 | 未验证 |
| T03.1 未知执行恢复 | R5 | 按实际窄窗口开展 | 待定位后决定 | 待验证 | 按影响范围判断 | 未验证 |
| T04.1 验收取证正反例 | R2 | 合格、规则遗漏及方向错误已验证 | 已补精确读取及证据识别 | 原生独立上下文实际读取 | 公开有界正反例正确区分 | 未验证 |
| T04.2 代表性完整语义 | R1、R4 | 待开始 | 按失败层决定 | 待验证 | 待验证 | 未验证 |
| T05.1 共享变化影响集 | R3 | 共享解释及遗漏依赖已有对照 | 已补方法指导 | 新上下文修订／重审已发生 | 公开工程范围 3/3 PASS | 未验证 |
| T05.2 消费、总览与接续 | R3 | 待开始 | 发现缺陷后决定 | 待验证 | 待验证 | 未验证 |
| T06 全任务降耗 | R4 | 待开始 | 依据真实成本决定 | 待验证 | 质量不降低待证明 | 未验证 |
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

- 新增 `check-unit` 和父级 self-check 的可选 `review_units`：沿原子单元、原候选、来源 digest、work generation 和实际模型版本启动有界生产读回；只读 RDF，工作空间可维护。Host 保持唯一模型执行方。
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
