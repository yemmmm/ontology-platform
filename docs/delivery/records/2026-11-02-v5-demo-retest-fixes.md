# v5 Demo 复盘问题修复记录

日期：2026-11-02。状态：工程回归通过，真实 Demo 修后验证中。

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

沿原题 32 冻结单题有界独立复核（非新业务题），revision 4 在完整读取下 **REVISE 0/1**，定位角色职责与接口映射实际缺口。主报告原 PASS 保留，但不采纳为完整业务接受。计划保留 revision 4 平台快照，生产仅接收公开原目标与通用方法重审说明，不接收私有题、答案、评审理由或另一上下文读取；沿同一 run／预算进行实质修模轮 2，最终仍复用原完整 36 题。

待追加：最终实际采用、独立语义结果、用量／预算与资源收尾。工程通过不代表完整 Demo 语义通过或净降耗。外部评分服务内部故障根因未获证，本次只改精确 IRI 回退与完整性反馈；不能声称外部故障已经修好。未知 Host／内部辅助用量继续保留，不新增计量框架或把未知补零。
