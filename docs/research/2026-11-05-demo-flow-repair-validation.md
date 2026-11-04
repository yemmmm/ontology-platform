# 新一轮Demo：流程修订真实验证

日期：2026-11-05（Asia/Singapore）。本轮已因预算关闭而停稳，结论为 **PARTIAL**。

权威范围：[R5.0-012](../requirements/requirements-v5.0.md#r5-0-012)；待验证[流程设计](../delivery/designs/2026-11-04-role-team-flow-repair-design.md)。

## 结论与完成边界

本轮在新建的Project/Ontology上冷启动。范围计划、公开CQ和Modeler更新候选已正式接纳；
同一原生线程接续、真实读取证明复用、精确候选正文引用复用均有实际采用证据。
但Coordinator整合被`contribution_shared_conflict`阻断，尚未应用，最终快照为revision 0、实际资源0。
**L0未闭环；独立L1执行0/36；L2未执行。不能由平台/交付合同失败推导模型语义质量差，也不能宣称质量有保证。**

预算授权3 CNY，结算估算3.28601132 CNY，余额-0.28601132；超出部分为关闭时已在途回合尾账。
账本`paused_confirmed`，准入关闭，活动、在途及待结算均为0；12个执行用量均已知，无未知/临时估算项。
未自动加额、未新建替代run、未删除原scope或清理恢复现场。独立评价器未启动。

## 配置、授权与独立边界

- Run：`workspaces/v5-runs/demo-role-high-20261105-start1`。
- 输入、稳定预算、私有冻结包及报告：`workspaces/v5-runs/demo-role-high-20261105-inputs`。
- Project：`d62ac836-d193-4a00-9849-e0eb69893b08`；Ontology：`a5833819-e4ca-492d-8b14-e5fd175c104b`。
- 入口`scripts/modeling`，合同`role-team/v1`，并发2；Coordinator、公开CQ、Modeler职责分离。
  Coordinator实际选择一个Modeler负责两个关联业务范围；没有为角色数量增加Modeler。
- 所有实际托管调用均`glm-direct / glm-5.3-flash / high`，生产及过程评价共12次原生执行；技术重试共享线程。
- 基线`57def2d`，运行中窄反馈修复提交`414d932`、`9b127f4`；最后冲突声明提示澄清尚未获得真实恢复证据。
  冻结角色方法不追改，恢复CLI读取本次技术反馈实现；Host不改候选、源材料或私有标准。
- 仅复用获准Demo v2范围、业务、API、schema及公开draft CQ。旧模型、候选、PASS和预算余额不继承。
- 私有冻结标准仍为36题，freeze_id=`v5-demo-role-high-36-20261104`，SHA256：
  `18a435959ef7b6cb4aa35ba6881042ad5f3acf252e568d4202f082a96183aca2`。
  Host未读私有题目/答案，生产未读评分；公开补题不改冻结分母。
- 金额模式不套三轮上限；本轮初建1轮、fresh production start 1；7个Modeler原生回合含阶段切换及4次技术纠错，不能重复扣成7个初建轮。

## 实际推进和主要问题

| 阶段/修复 | 实际证据与结果 |
| --- | --- |
| 安全启动 | 首Modeler来源分析16:55:18Z开始，授权接收仅有16:52Z保守记录，约3分18秒；未前置mock、全面审计或harness |
| 范围/CQ | 首scope接纳；公开Q1–Q9保持draft，并补CQ10–CQ20；过程分数不回灌生产 |
| 首提案 | `modeler--role-00002`正式接纳，24分52秒；114项均显式提供中立字段，补null分支未触发 |
| 新公开CQ输入 | 在忙碌回合自然边界重入`00004`，20分09秒；该业务版本变化不能冒充同基线技术纠错 |
| JSON语法 | 约7.5万字符交付内部语法错误；恢复分支丢弃已有json_error，Agent误改文字前缀。414d932透传真实行列/位置 |
| 信封形状 | 修正语法后根对象提前闭合，source_refs/issues/consumed_ids落到根外；9b127f4补未匹配片段的字段诊断，接纳条件未放宽 |
| 引用类型 | 将execution读取证明误放入basis.consumed_refs，得到role_material_not_consumed；新增权威提示区分执行证明与真正材料引用，无新守卫 |
| 正文引用复用 | `00008`以artifact=null+确切retained_artifact_ref重交，2818字符、2分24秒，正式接纳；保持原作者/原正文摘要97d025… |
| 根整合 | `role-00001`原生15分34秒，22次交接材料与7次源读取调用；计划选择116项/122个create变更，但程序尚未安装/应用 |
| 最后阻塞 | Modeler的shared_conflicts非空，混入共享定义说明、后续绑定依赖、版本注意事项；程序保留原属主modeler及可恢复错误，不猜测这些自然语言是否意味着已解决 |

同原生线程接续与累计usage baseline取差已实际采用。`00005`未重读原始业务材料（0次read_material），
`00008`真正复用了已保留正文。2818字符与约7.5万字符的差异只证明局部包装机制采用，
**不能替代整任务token净下降、纯语义有效工时或独立质量证据**。

原始JSON无法解析时没有可直接复用的正文对象，故多次仍需完整重交；新增CQ业务版本也引起新上下文及成果重读。
这些成本未因读取复用自动消失。Host实际做了两次技术位置交接与窄实现修复，本轮不记为无人补位自主交付PASS。

## 最后阻塞的T0复核与后续修正

明确声明的未解决共享定义冲突直接关系模型正确性，不能删除该守卫或由Host清空原作者数组；
原子apply可以保护写入一致性，不能替代业务冲突判断。当前返回可恢复错误且未写入，不是永久run拒绝。
原Modeler可以区分真实不兼容定义与已定责任/未来依赖，保留相关事实后纠正交付声明。

本轮已在动态权威prompt中明确：`shared_conflicts`仅声明真实未解决的不兼容共享定义，
已定维护责任、待丰富内容、依赖及版本说明放入署名工作记录。此项为prompt-contract修正，
未改变接纳条件，也未修改保留工件；因预算已关闭，**真实恢复尚未验证**。

下一步须沿同一budget_ref获得新金额授权，再由Coordinator交原Modeler澄清冲突声明，
继续原整合、应用、原属主/CQ/整体自查，最后用同一冻结36题独立验收；不创建新run绕过账本。
未触发的中立补null、应用后纯model_support分流、多Modeler共享冲突/递归场景保持未观察。

## 耗时与完整已知用量

原生执行窗口：本地11-05 **00:55:14—02:45:33，墙钟1小时50分19秒**；
用量统计截止UTC18:48:14，即本地02:48:14；封存记录约02:54。
从00:52保守授权记录到02:54收尾约2小时2分，接收起点不精确；后续只读封存/文档时间已单列，不冒充原生执行时间。
授权接收时间不是精确事件时间，不把上述窗口称为精确的整段对话总耗时。

- 生产相关原生窗口并集68分21秒，技术纠错原生窗口27分15秒，过程评价窗口10分10秒。
- 过程评价与生产并行，三者不能直接相加为墙钟；全部原生窗口并集约95分36秒，累计Agent时间约123分08秒（按秒级事件边界）。
- 原生窗口包含推理、provider等待、工具及输出，不等于纯语义有效劳动；人工诊断、记录、等待、准备/封存的有效工时未单独计量。
- 首次错误环境全量回归15分40.67秒；补正后16分13.41秒。测试与生产及彼此并行，不追加到总墙钟。

| 角色 | 输入token | 输出token | 输入+输出 | 金额估算CNY |
| --- | ---: | ---: | ---: | ---: |
| Modeler | 4,756,767 | 340,513 | 5,097,280 | 2.31792428 |
| Coordinator | 1,342,771 | 80,336 | 1,423,107 | 0.53854188 |
| 公开CQ | 340,494 | 44,965 | 385,459 | 0.25962696 |
| 过程评价 | 204,331 | 28,872 | 233,203 | 0.16991820 |
| 已知合计 | 6,644,363 | 494,686 | **7,139,049** | **3.28601132** |

输入中含缓存5,446,016；输出中含推理278,695，均不重复加总。纳入全部失败、被取代和恢复执行，
恢复段按native-usage-baseline取差；没有把共享线程累计末值重复相加。托管用量覆盖完整。
外部Host用量unknown，按用户规则不计任务费用或预算；金额为冻结价表估算，不是provider账单。

## 工程检查、过程评价与独立验收分开

- 新增位置透传回归先红（KeyError json_error）后绿；相关72项通过，190.64秒。
- 新增尾随metadata诊断回归先红（KeyError schema_errors）后绿；定向40项通过。
- 首次全量430通过/3失败，原因是本次测试命令漏根目录PYTHONPATH；补环境后对应文件4项通过。
  按真实CLI导入环境完整复跑：**433通过/1条依赖库警告**，973.41秒；两份原日志均保留。
  README补测试导入环境，未改产品导入实现。
- Ruff check、format和差分检查通过。无backend/frontend代码改动，不需要服务重启。
- GitNexus未索引本次v5符号，staged分析低风险但0个符号映射；采用直接调用点、差分与回归，不声称图覆盖。
- slicing过程评价satisfied，四维4分；CQ评价gaps，覆盖3分/low，其余三维4分。
  integration未观察；过程report的evaluation_complete只对应已提交诊断，不代表三阶段或语义验收完成。
- 独立36题执行0，未产生有效裁决；未以工程PASS或过程评分代替L1。

## 原始证据与恢复入口

- 本轮输入目录：`workspaces/v5-runs/demo-role-high-20261105-inputs`。
- 预算/停止状态：`status-budget-closed.json`、`status-final.json`；稳定预算`task-budget`。
- 实际平台快照：snapshot_id=`3321871572964ab7819882db2d8ff4d0`，`snapshot-budget-close.json`回执；
  model_revisions=0、resource_refs=0、model_read_error=null。私有快照含临时绑定，未提交版本库。
- 计量：`execution-statistics.json`、逐执行`usage.jsonl`/`native-usage-baseline.json`/原生events及任务预算账本。
- 过程评价：`process-jobs.json`、`process-slicing-result.json`、`process-cq-result.json`、`process-summary-receipt.json`。
- 失败与技术交接：`json-syntax-diagnostic.json`、`json-envelope-diagnostic.json`、host-technical消息/回执；
  `resume-format1…4.log`与原执行result均保留。
- 工程回归：`full-v5-regression.log`、`full-v5-regression-corrected.log`；修复提交414d932、9b127f4。
- 压缩接续：`NEW-RUN-HANDOFF.md`仅保留本轮信息。项目/本体/检查点保留，未stop或cleanup未完成任务。
