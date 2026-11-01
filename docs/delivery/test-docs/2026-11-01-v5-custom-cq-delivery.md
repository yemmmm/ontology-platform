# R5.0-010 自定义 CQ 实施与验证记录

日期：2026-11-01。用户已同意按[设计](../designs/2026-11-01-v5-custom-cq-design.md)实施。
状态：功能实现、工程验证及真实元数据／界面运行验证完成；同日后继新授权的九题 GLM
运行与检查点接续已完成，独立能力核对为 PARTIAL，见文末。尚未形成九题正式通过结论。

## 范围

复用平台 CQ，增加项目问题、可选标准、版本与导入；总览编辑／选题；v5 固定公开目标、
来源变化、冻结及分层报告。保留原 CQ 和旧 run，保护工作区其他四个文档改动。
不启动或恢复已封口建模，不追加旧预算，不修改业务模型与 Demo 事件数据。

## 已知影响

GitNexus 对平台 create_question 返回 LOW；同名 validate_report 命中旧栈并返回 CRITICAL，
已告知用户，旧栈文件不修改。实际 v5 验证器未索引，沿定向调用检查和相关回归取证。

提交前 detect_changes 对共享 schema 报 **CRITICAL／267 流程**，已再次告知用户。
核实索引停留 2026-09-15／50d54d2，61 个符号中 49 个归到 schema，包含本次未编辑的
reason 等通用字段及已退役页面；不能当作当前精确调用图。定向检查了权限映射、批次 CQ
引用、工作流资源引用、总览计数、旧 Lineage 和 checkpoint remap：前四者按 Project
或显式可空 Ontology 处理，旧 Lineage 只收本体匹配项，remap 保留 None。本次没有更改这些
调用方，也不声称取得图覆盖。当前回归和实际读取支持本次兼容范围；旧索引的原始风险
结论不伪改为 LOW，见[影响核对](../evidence/2026-11-01-custom-cq/impact-review.json)。

## 测试轮次

- 后端先写七项行为测试：首次 6 failed／1 passed，失败为原接口强制 ontology_id 和缺少
  导入入口。增加实现后，相关范围 31 passed／1 skipped／1 fixture error；错误是隔离
  路由未注入 RDF 依赖，已修正测试依赖，无需业务修补。后续结果继续追加。
- UI 先写问题保存／编辑／选题、版本冲突保留草稿两项交互测试；首题因尚无入口超时，
  不是运行基础设施故障。后续构建和交互结果待记录。

后续测试轮次及修正：

- 后端相关范围最终 **37 passed／1 skipped**，含项目授权、完整 CRUD／种子、历史结果、
  真实 PostgreSQL 迁移和两个 session 的旧版本冲突。修正隔离路由测试依赖后，未改变旧验证。
  又以失败测试确认 Host 会将 CQ 选题错误误归基础设施，现保留 cq_selection_unavailable；
  同内容换 actor 原本递增版本，已修复，避免无意义的建模重入。
- 后端全量 **1279 passed／56 skipped**（1335 项，779.94 秒）。跳过项来自既有可选／
  集成前置，不记为通过；保留原日志。45966 条告警主要为现有 RDFLib／FastAPI 废弃接口。
  全量后最终相关变更由上述 37 项覆盖，不用旧结果冒充新代码。
- v5 全量 **237 passed**（125.52 秒，无跳过）；增加每次选题／停止请求及修正 Host 合同
  后，最终相关 **46 passed**（9.09 秒）。真实 PostgreSQL／checkpoint，外部 Agent 使用
  确定性 actor：证明自然边界、旧候选不应用、完整题集、独立只读上下文和固定版本重试，
  不证明 GLM 的业务语义质量。另修正 cq-sync 在读取状态前没有处理排队 stop 的问题。
- UI 初轮 31 passed／1 failed：旧 T14 一律禁止 PATCH，与本次已获准 CQ 编辑冲突；
  权威需求明确 CQ 例外后，将断言收窄，保留模型 CRUD／旧页面退役检查。最终构建通过，
  **32 项 Playwright 通过**，覆盖新增、编辑、版本冲突保留草稿、选用、停用、JSON 导入、
  下载、导航／语言与手机布局。修复受控复选框的即时反馈、编辑表单标签及中文状态显示。

## 真实运行与交付

本地 Alembic 从 0036 升至 **0037_custom_cq**；隔离 schema 的预验证保留旧 CQ 行、
检查唯一约束和版本冲突。完成必要测试后重启 ontology-platform.service，前后端健康。
真实浏览器检查覆盖 1440px 桌面及 390px 手机，九题均显示待核对、未执行，手机无横向溢出。

九题已导入 Project `40841ac8-1c93-4cb1-85ba-1a9e8fb7928b`，重复导入保持九个原生 CQ ID。
Host 实际进程验证选取两题及无效选题的类型化错误；从真实材料固定完整九题包。
快照为 `cq-8009b19cc11b98d079c5a1a0`。入库／冻结／界面操作前后，Ontology
`755f1e0e-cf5d-47f2-a2a3-95220f4cba96` 均为 revision 4、14 资源，没有修改业务模型。
各次临时管理员凭据均已撤销，未保留明文；技术验证只准备 Host 元数据，不调用 Provider。

可审阅证据：[真实元数据检查](../evidence/2026-11-01-custom-cq/runtime-verification.json)、
[真实界面检查](../evidence/2026-11-01-custom-cq/ui-verification.json)。
界面截图：[桌面](../evidence/2026-11-01-custom-cq/overview-desktop.png)、
[手机](../evidence/2026-11-01-custom-cq/overview-mobile.png)。
完整日志、公开快照、
冻结包、Host 输入／失败原件和截图保留在
`workspaces/v5-runs/custom-cq-delivery-20261101-inputs/`，不提交数据库或凭据。

## 使用与证据边界

用户从项目总览的“项目能力问题”添加／编辑，答案与来源均可后补，内部工作单元不出现在表单。
新任务按 project_ref 默认读取选用 CQ，显式 custom_cq 可启用／禁用；单次范围支持
cq_question_ids。cq-sync 只排队，cq-evaluate 沿既有预算及独立只读执行冻结追加批次。
同一 evaluation-id 不改旧题集；公开分层摘要只写回匹配 CQ 版本，答案及私有理由不公开。

九题的标准仍是 **draft**，不是用户逐条确认的业务真值。Agent 可以按获准材料通过既有
语义记录／HITL 起草和澄清，用户在编辑入口确认标准与来源；本轮没有验证该真实 GLM
交互过程，也没有执行新的独立 CQ 语义或实际 SQL。界面／协议通过不能变成九题语义 PASS。
Q3／Q4 的编码、Q7 的时间和 Q8／Q9 的事件来源等原缺口，没有由此次功能实施自动补齐。
没有恢复旧 run、增加预算或改变旧验收报告；隐藏题仍沿原私有准备／冻结通道。

## 同日后继真实 GLM 验证（另一次用户授权）

用户后续要求继续 Demo v5、将九题用于 CQ，并验证不同进度添加与检查点接续，额度由
Host 控制。新工作空间绑定原 Demo 模型，独立 3 CNY 账本；旧封口运行、预算和历史验收
保持。复用九个已保存 CQ，先选 Q1—Q3，真实忙碌回合中加入 Q4—Q6，停稳保存检查点后
加入 Q7—Q9。三份固定目标分别被实际 GLM 完整读取，暂停时保存／同步未自动恢复，
随后显式沿同一 run 接续。

实际发现首次 CQ 来源激活会把 prepare 改成 model，导致 prepare-only 后 resume 返回
platform_scope_not_prepared。保留平台授权准备，仅修复尚无 baseline_ref 时继续 prepare；
新增红测后相关 32 passed，完整 v5 **239 passed／无 skip／1 条既有 warning**。
现存失败工作以带前置条件的 Host 技术记录恢复，没有修改候选或业务模型。

三个生产候选均 no_change；一次范围澄清后自查与 handoff 完成，四个业务问题仍未回答。
独立评价先因缺原始材料读取、再因将 draft 标准标为 pass 被可恢复拒绝；原件保留，
沿相同冻结只纠正读取和报告合同。第三个新只读 GLM 上下文实际读齐九份材料并查询模型，
最终 **PARTIAL、0/9 正式通过**。模型信息／SQL 支撑为四题支持、三题条件支持、两题
不支持；九题 criteria_status 仍 draft，sql_execution 均 not_run。九份匹配版本摘要已
写回项目，skipped_stale=[]，独立理由的编码概括偏宽也在完整记录中保留限制。

最终仍为 revision 4／14 资源／4 个历史 Batch；九个稳定 CQ ID 全部 active／selected，
重复导入不增加 ID。支出估算 **0.652301 CNY／3 CNY**，provisional=0，八份已知原生用量
覆盖 complete；外部 Host 和未归集辅助用量仍单列，非提供商最终账单。
新 run 已 stop／cleanup，原模型保留，两份读取及协议／管理凭据均核实撤销。

这是公开 Demo 的有界目标接入与能力核对，不是完整业务盲测、全部写入故障窗口或无人补位
自动交付。完整原件、阶段、耗时和限制见
[真实验证记录](../../research/2026-11-01-v5-demo-cq-live-validation.md)，
[可审阅汇总](../evidence/2026-11-01-v5-demo-cq-live/summary.json)。
