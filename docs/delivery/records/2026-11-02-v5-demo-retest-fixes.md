# v5 Demo 复盘问题修复记录

日期：2026-11-02—03。状态：工程修复及相关回归通过；最终独立语义验收 **PARTIAL 34/36**；运行停止、模型保留、临时凭据已清理。

用户授权修复[复盘](../../research/2026-11-02-demo-glm-repeat-retrospective.md)列出的已定位问题。归属 R5.0-001／003／004／006／007 及继承的 R4.3-024／025 合同。保持 GLM Flash／low、原业务材料与 36 题标准；历史运行及失败原件只读保留，独立验收不参与生产修模。

本次范围：对齐资源读取选择器和 scope；核对冻结来源分页与实际定义正文覆盖，返回可恢复补读反馈；缩窄普通报告合同并让独立报告纠错复用自身上下文；复用已有覆盖记录加强 S7／Judge 的实际表达核对；补齐当前映射字段的通用合同例子。已修租约路径复用既有证据，不删除授权、版本、原子性或未知写入保护。

采用标准交付。先用保留反例和相关测试证明失败，再做最小修复。共享执行／验收代码变更后做 v5 组件回归；真实读取／原生上下文合同另作有界验证。工程、独立语义及净效果分别报告，不以程序替业务 Agent 判定含义。

GitNexus 同名 `validate_report` 命中旧 `modeling_team/acceptance.py` 并返回 CRITICAL；已向用户告知。按完整 v5 文件身份查询均未索引（UNKNOWN），本次以 v5 调用点和组件检查确定影响，不能宣称图谱覆盖。主要调用方为 CLI 独立评价、root／unit 自查、总览及原生 Agent 接入；后端原读取 API 和旧 Runner 不改。

已实施：

- `resource-list` 支持省略 IRI 取得全量清单，精确 family 缺 IRI 返回可恢复错误；结果明确 read_scope，关系仍沿后端整本体合同。
- 在既有读取原件中合并同 ID／SHA256 字符区间，识别 query 的 fact、resource 及 detail 正文形态。完整模型检查显式采用 whole_model；根自查／独立 PASS 的读取缺口可补读或保留 PARTIAL，不自动判业务语义。
- 普通报告只提供五项必要逐题字段；严格 JSON 错误返回行／列／位置。纠错沿同一冻结评价恢复自己的 thread，历史事件不覆盖；不同 thread 不可合并证明。原生 home 持续沿最初会话，第三次恢复仍保留身份。
- 金额账本沿原累计前值取差；缺基线不能补零。映射示例补充物理列 role=value、允许省略 property_iri 及 column_mappings 对应条件；示例经真实编译器验证。
- S7／Judge 提示要求核对条件原义、职责／参与、接口属性绑定及实际定义／定向关联，延用既有记录，不新增视角配额或连通性裁判。

开发验证：先保留失败用例，再实现修复。完整 v5 回归 **268 passed**（346.20 秒，无跳过）；随后新增跨 thread 拒绝反例及最终提示／文档调整，相关读取与验收回归 **52 passed**（16.88 秒）。覆盖合并、普通报告合同、原生恢复目录链、累计差值、根自查缺口及可编译映射均有直接用例。修改 Python 文件 Ruff 与 diff whitespace 检查通过。全目录 Ruff 的四项问题在未改动的 worker.py／test_custom_cq.py，已用 HEAD 原件重现，不扩大本次修复。

有界实测：新隔离任务 `demo-glm-fixes-20261102-start1`，原公开五项材料及原冻结 36 题，原题哈希保持；不注入前轮模型、候选、Host 语义反馈或隐藏答案。所有托管角色继续 GLM Flash／low，独立 3 CNY 金额账本；显式 whole_model，独立 runtime-observations 作为 required-artifact。输入／授权／测试日志保存在 `workspaces/v5-runs/demo-glm-fixes-20261102-inputs/`。旧运行与模型保留，不重开已撤销凭据。

实现提交：`e65b5ed`。GitNexus staged 检查识别 20 个变更文件、零已索引符号／流程；不据其 low 投影声称 v5 调用图覆盖。文档 80 个相对文件链接与 JSON 合同检查通过。只修改 v5 和指令／合同文件，无后端／前端代码变更，不需应用服务重启。

真实 SDK 接续探针：使用已完成的首个生产 thread，只调用 thread/resume，不调用 turn/start、无模型推理。恢复为同一实际 thread；原 events、thread-binding、result、usage 四份文件哈希逐一保持，临时配置恢复原值。原件见输入目录 `native-resume-probe/summary.json`。这证明新执行目录能恢复原 native home；付费报告纠错与累计差分的实际路径是否触发另记，不把无推理探针当语义验收。

生产截至第三批：首次应用 27 项，自查返回 revise；一批 relation_type 缺 source_class_id／target_class_id 被准确拒绝并返回 retryable 字段位置，Agent 沿原运行自行修正；后继 9 项、8 项已实际应用。分批引用依赖不重复计为新的 fresh start。原生 API 读取已实际续读 12000 字符之后部分；物理列 role=value／省略 property_iri 例子已被 Agent 采用。尚未据此判断最终语义完整性。

实测追加窄修：`apply-00004` 的 11 条定义关系因已核实 relation_type 谓词被 `_predicate` 错限为 property 而 not_written。底层 create_relation 接受该 ObjectProperty；这是 platform-contract，不是模型质量失败。T0 复核确认类型约束仍有必要，但合法 relation_type 被误拒；本次只放入该合法种类，继续拒绝 Class／entity 谓词，保留身份、范围、修订、原子性与业务验收。GitNexus 对完整文件限定符仍 UNKNOWN，直接调用点为 legacy Runner 与 v5 Host worker。

新反例先以 relation_type 唯一失败（其他三例通过），修后 compiler／提交／引用相关 **107 passed**，v5 Host 调用链与技术合同 **37 passed**。持久合同补充已有 relation_type 可作谓词，无需重复 property。运行按自然边界暂停，失败与待应用技术替代候选保留；Host 用 source-revise 交接署名的 `platform-contract-update`，由 Agent 重新选择表达。原五项业务来源、题目内容和金额账本保持；后半段属于公开技术修复后继续，不能冒充零介入冷启动。此次继续不新增 fresh start，也不由 Host 改写候选。

该追加修复提交为 `aaa0b62`。随后真实 `apply-00006` 复用既有 relation_type，11 条 relation 成功应用，未应用重复 property 替代候选。原自查再次 raw ready 时，读取覆盖检查准确发现六项来源未读、缺全量 inventory（仅返回 30 个正文），拒绝交接并给出可补读缺口。补读回合 `self-check-00006-001` 沿原目标读取六项来源全文、44/44 资源正文及 51 条完整关系，revision 4 最终 handoff_ready；这仍是生产自查，不是独立语义 PASS。

接续中另保留一次账本 metering_error 暂停（source/upstream offset=0，原事件 seq=588）。本轮不推断缺少轨迹的深层原因。后继 11 个托管执行全部实际数字补齐，unknown/provisional/pending/inflight 均为零、已知估算 0.83328392 CNY，Host 沿既有 continue_authorized 仅清除已恢复的 metering_error，保留事件与 3 CNY 额度。此时发现 CLI resume 没有刷新账本投影，旧 budget_open=false 阻止推进；以新反例复现后，在既有 resume 入口补一次 synchronize_budget。预算、控制、HITL、来源修订 **34 passed**（66.71 秒）；不自动清除真实错误、越额或用户暂停。

原 36 题独立评价 `fixes-full-36` 已启动，额外 runtime-observations 显式必读。原问题哈希保持，独立者不接收生产候选、自查与私有修复答案。

独立报告纠错的真实路径已验证：attempt 0 raw 36/36 PASS，但 runtime-observations 缺 `[12000,13393)`，程序拒绝 PASS；attempt 1 恢复同一实际 thread `01a19cfc-b892-7b32-b1b9-12fc359a57d0`，原生 home 沿首回合，唯一新增读取就是该缺页，复用自身先前读取后形成 coverage complete 的 36/36 报告。原回合与纠错事件分开保留，实际累计前值另存，费用按差分结算。

该报告仍存在语义判据替代：多视角题仅以 applicability／范围排除项为理由，未逐项核对其要求。Host 没有将读证齐全升级为业务通过。补充通用方法要求复合标准逐项给出实际发现，区分业务职责／参与和一般谓词、接口字段绑定和数据库列映射；修改生产方法、S7 和 Judge 权威提示，保持自由表达和既有 coverage，不新增节点配额或输出模板。相关框架回归 **74 passed**（92.30 秒）。

通用逐项核对提交为 `68cc310`。第二轮实际发生的格式／载体问题另保留：apply-00007／00009／00010 在写前拒绝重复 business_meaning 不一致、relation_type 缺有效 Class 端点、update_entity 不支持 classes。Agent 自行修正后 apply-00008 应用 24 个接口／管理普通定义及 2 个 Class，apply-00011 应用 5 项谓词／修正；仍有绑定边待应用，不宣称这些应用已完成语义交付。

重复踩中 Class 端点／mutation 形状的原因属于技术提示采用缺口，已收窄权威说明：无统一 Class 域/值域的普通定义连接可用 candidate property（predicate_kind=relation）并同批引用；不必发明 Class 填槽，update_entity 不能照抄 create/read 的 classes；完整 business_meaning 放 item 层，通常省略可选的内层副本，重复时必须完整一致。代码校验不猜业务含义。Host 沿现有队列送出署名 source=host 的技术补充，已由原单元消费，不冒充 user，也不作为独立者业务依据。此说明已持久化，实际新默认冷启动效果仍待后续授权验证。

沿原题 32 冻结单题有界独立复核（非新业务题），revision 4 在完整读取下 **REVISE 0/1**，报告角色职责与接口映射缺口。该单题首版提示曾使用 Actor 措辞，后续已纠正为原方法允许的职责或参与表达；不能把缺 Actor 节点本身作为失败证据，接口属性绑定缺口有实际定义对照。主报告原 PASS 保留，但不采纳为完整业务接受。revision 4 平台快照 `247d83b716e44a1fb6e732070c476d7f` 保留；生产仅接收公开原目标与通用方法重审说明，不接收私有题、答案、评审理由或另一上下文读取；沿同一 run／预算进行实质修模轮 2，最终仍复用原完整 36 题。

第二轮最终 `apply-00012` 因仅给字段、没有统一候选被写前拒绝；Agent 自行修正，`apply-00013` 实际应用 66 条关系，revision 7 共 75 个定义、123 条读模型关系。`fixes-round2-full-36` 首回合 raw 36/36 但 API 材料少读末页；同一独立上下文补读后正式 36/36、读取完整。`fixes-original32-postrepair` 同样先拒绝三项未读公开材料，补读后正式 1/1、全模型读取完整。所有失败原件保留，读取齐全不证明评判无误。

上述评审仍漏过四个普通“定义适用于……”谓词错误声明 business_role。Host 通过实际治理读回记录该可观察问题，修订公开 `role-declaration-review`；没有替建模 Agent 选择新分类。生产、S7 及独立提示均要求全模型完整性审查核对每个 semantic_role 声明，不能用另一处正确职责掩盖这四处。来源支持的业务参与关系仍可表达 role，不强制 Actor 载体。

实质修模轮 3 中，`apply-00014` 请求封装多字段被写前拒绝，`apply-00015` 成功将四处 business_role 改为 Agent 自选的 applicability，模型 revision 8。`role-delta-and-read-target.json` 比较证明：75 个资源身份保持，四处除 semantic_role 外的 semantic_definition 全部逐字段相同。`self-check-00015-002` 读全八项当前来源、75 个正文及关系后 handoff_ready。计为 1 次 fresh semantic start、3 轮实质建模；技术重试和补读不另计轮次。

补读返工另作两处局部降耗：材料默认页由 12000 增至 16000 字符，显式分页和完整性义务不变；独立 `target` 移除写入回执引用，whole_model 通过实际清单定位资源，完整 handoff／冻结修订及权限验证保留。当前目标 JSON 从 94603 字符缩至 176 字符只是元数据大小结果，不能称为全任务净节省。新投影两例先失败再通过，读取／验收相关 **54 passed**（17.37 秒），全声明提示相关 **44 passed**（49.99 秒）；前者覆盖默认分页调整后的 **52 passed**。完整 268 项回归后新增改动按其相关用例验证，没有声称重跑完整新增总数。

最后独立评价 `fixes-final-role-full-36` 在 revision 8 使用原完整 36 题、同八项公开来源及显式必读 runtime-observations；独立者没有生产候选或自查。外部评分服务内部故障根因未获证，本次只改精确 IRI 回退与完整性反馈；不能声称外部故障已经修好。未知 Host／内部辅助用量继续保留，不新增计量框架或把未知补零。

最终正式报告 **PARTIAL 34/36**。两项未通过为原题 20 的全范围完整性、原题 36 的全图关系核对，评审明确保留检索证据缺口，未确认新增模型错误。原始工具返回具备全部来源、75 个正文和 123 条关系，程序的 read_coverage.complete=true 只证明这些原件可得；原生会话中的 resource-list 实际有 `…77614 chars truncated…`，resource-relations 有 `…85767 chars truncated…`，不能据原始响应完整推定 Agent 已逐项消费。直接可见证据另存 `native-consumption-evidence.json`。此处保留 PARTIAL，既不要求平台替 Agent 判断语义，也不把早先 revision 7 的 PASS 迁移到 revision 8。原生长结果的有界消费与两项最终完整核查尚未闭环。

最终已知原生用量完整覆盖 34 次执行：生产建模 16、自查 10、独立验收 8。累计输入 **12,311,346**（其中缓存输入 10,447,744，已包含在输入内），输出 **245,234**，合计 **12,556,580 token**；恢复回合扣除实际累计前值。全部原生执行区间并集 **4,950.524 秒（约 82 分 31 秒）**，从首次开始到最后结束的墙钟窗口 **8,080.833 秒（约 2 小时 14 分 41 秒）**。建模、自查、独立验收各为 2,862.958／723.784／1,363.782 秒，含工具与服务等待，不当作有效语义工时；工程、Host 与内部辅助有效工时未完整核实，不扩展平台或 harness。

同一 3 CNY 账本最终估算 **3.05349288 CNY**，在最后一个已准入原生回合结算后超出 **0.05349288 CNY**，remaining=-0.05349288、budget_exhausted，后续准入关闭；没有追加授权、换账本或再启动付费修模／验收。价格为固定三桶估算，非供应商最终账单。托管原生 unknown／provisional／pending／inflight 均为零；外部 Host 按用户规则不计任务费用，原始用量未知，内部辅助也未完整归集，全任务计量仍 PARTIAL。没有等质量端点或单因素对照，不认定净降耗通过。

资源收尾：Project `1f7db044-bd0f-40f3-897b-897a32de96f6`、Ontology `6099de17-10fa-49f0-9a4a-465421bf05d5` 的 revision 8 模型保留；最终含平台数据快照 `d432e7d9a04d49bf847d3965343609ac`。stop 控制为 stopped、active={}；cleanup 回执确认所有本次 Session 终结、无在途尝试、项目读取／Protocol／组织管理员密钥均撤销，written-retained。失败候选、拒绝回执、原始评审、旧快照与预算暂停事件保留。收尾原件见输入目录 snapshot-final／budget-final／stop-final／cleanup-final／status-final.json，逐角色用量见 observed-usage-summary.json。

本次关闭已定位工程缺陷及其相关回归，不关闭完整 Demo 语义接受、默认冷启动自主稳定性、重复性、通用 Judge 可靠性或全任务净效果。下一次付费验证需要新的明确预算授权，不能借技术重试绕过当前耗尽边界；本次到此停止真实运行。

最终收尾检查：当前修改的五个 Python 文件 Ruff／format、diff whitespace 及七份文档 230 个相对文件链接通过。GitNexus staged 分析识别 12 个文件、零已索引符号／流程，不据 low 投影声明 v5 图谱覆盖。仅提交本次文件，保留其他调研改动；本轮未修改 backend／frontend，不需应用服务重启。
