# Delivery token 优化：首批修复与三任务验证

用户授权按上一轮建议修改，再由Codex执行建模、复盘并继续迭代。总计最多3个建模任务，
每任务最多3轮建模机会；生产、Delivery、CQ、独立Consumer／Judge及外层Codex Host
固定`glm-5.3-flash / low`。本次复用R4.3-026最小安装链原完整范围，不降低评分或分母。

## 首批范围与实现

归属R4.3-019／022／029／030，依据
[前轮输入复盘](../modeling-retrospectives/2026-10-18-codex-flashx-low-retrospective.md)。

- 同一provider wait按wait_id／epoch识别。首次错误及Host恢复待办保持，同一状态不反复
  发起必然被冻结Profile拒绝的升级；wait清除／新epoch后重新处理。未新增CQ通信权限、
  次数硬门或自动重启；原正式issue与Host恢复路径保留。
- CQ可恢复码`cq_waiting_provider`补入既有注册表。已批准slice通知因同一provider wait
  被拒时不每drain重发，wait清除／变化后继续；普通错误仍可重试，不永久关闭run。
- 增量输入省略未变化task_context及run identity，实际变化、授权、未知写入和必要当前
  状态仍提供；bootstrap／恢复重新给完整上下文。原journal和分页确认不改写。
- coverage六个索引共享顶层精确evidence引用，使用`evidence_ref="evidence"`指向它；
  覆盖计数和省略说明保留。Delivery实际加载skill同步说明，不新增引用服务。

首批不启用030 F3短线程／F4机械动作，不恢复暂缓021。是否继续改动由每组真实证据决定，
不能用缓存率提高或离线体积减少代替净降耗，也不能把Host补位转移成本藏掉。

## 工程检查

新回归先在原实现确认失败，再实施修复：重复升级／CQ等待恢复、稳定上下文省略及
共享引用读取均覆盖。Delivery四文件定向192 passed；Runner provider／CQ定向分别
49、15、68、81 passed（各组有重叠，不相加），后者8 subtests passed。
另一会话只读复核Delivery diff及恢复／unknown边界，没有严重阻塞；不称语义验收。

Team全量：**3353 passed、12 skipped、318 subtests passed**，514.75秒，退出0；359项
既有弃用告警保留。测试前后源码摘要一致。原日志／JUnit及源码摘要在gitignored
`workspaces/token-optimization-20261019/`。GitNexus未索引两个修改入口，impact UNKNOWN；
调用点及定向回归用于当前影响核对。staged detect_changes为low，但主要运行入口覆盖
仍缺，不能声称图分析完整。只有modeling_team／skill改动，不需产品服务重启。

## 实验授权与执行责任

全局台账为`workspaces/token-optimization-20261019/authorization.json`，3任务各自核算
初建及验收后实质修模轮次，fresh semantic-start单列。成功不强行耗尽3轮；每组成功／
机会耗尽后关闭自己的operation／run／临时凭据，保留模型／冻结池／原证据。

独立Codex Host负责真实启动、监督、私有CQ审核、交接、收尾及只读复盘；外层主Agent
负责代码修复、监督和证据核对。隔离生产Team仍决定语义，独立Consumer／Judge只读验收，
Host复盘不代替最终裁决。全景审核与整池审核分开，不将隐藏问题反向送入生产修模。

每组采集所有实际线程的input／cached／uncached／output、压缩子集、响应数、Host
补位与自身用量、错误／读取及墙钟。缺原件保持unknown；缓存与推理不重复加总。
旧FlashX只作参考，后续三组使用相同Flash low配置；真实语义、L0、降耗和费用分别结论。
本记录先记工程与授权，实际每组run、模型身份、质量、token和优化决定随结果补记。

## Task 1 实测与第二批窄修

Task 1 为 `minimal-chain-20261019-token-opt-a-r1`，实际 semantic start 为
2026-10-18T18:21:08.061792Z，初建用1/3轮；公开1/1、隐藏3/3的独立非盲回归均
full_pass，模型revision 2。原Codex Host已完成私有复盘与收尾，原件位于
`workspaces/minimal-chain-20261019-token-opt-a/`。10个建模／验收最终线程的204个
去重响应记录input 17,224,297、cached 16,652,736、output 54,960，总计17,279,257；
Delivery为13,884,292。此处尚不包含外层Codex Host及工程线程，不能当全任务净成本。
部分中断provider请求缺数字用量，完整费用仍unknown；旧FlashX不同模型不作净收益对照。

本轮暴露两次CQ准备稿被当作正式审核后无法冻结、隐藏Judge重复提交pass＋非空
failure_layer，以及Host全景/整池标记和最终停止操作的技术缺口。原始失败不改写；
主Agent通过原Delivery输入通道纠正阶段/范围并完成最终停止控制，不能称全程自主。
CLEANED、Delivery/native退出0及bootstrap-cleanup真实撤回管理/只读密钥均有原件。

第二批只修上述已观察的合同返工，不启用F3/F4或恢复021：

- CQ非review阶段仅保留不可变私有稿，不创建Host审核请求、不改变当前CQ阶段；
  返回preparation_saved及准确重发指引。只有panorama-review/slice-review请求审核，
  同session可立即纠正重发；没有新增不可恢复拒绝。正式review、原题池与独立审核保持。
- CQ工具描述、动态输入和原JSON合同同步。报告字段校验不放宽；Judge遇空值纠正
  仍不能通过的inline提交，使用既有handoff材料＋report_ref完整替代输入，不反复
  重发同一无效payload，也不为适配编码改变裁决。
- 后两组复用已备脚本，固定backend虚拟环境、正确预算和真实起点、简明状态读取、
  全景/整池完成区分及明确最终停止。脚本是现有工具执行模板，不增语义裁判。

新增准备阶段回归先红后绿。CQ、投影、冻结、诊断及checkpoint恢复组148 passed／
3 skipped；report sink、独立验收、材料引用与能力合同组122 passed，均退出0。
本批合计270 passed／3 skipped；首批全量结果继续保留，不冒称本批重新全量3353项。
GitNexus仍未索引CQ发布入口，impact UNKNOWN；按直接调用点及上述边界回归检查。
工程结果不代替下一组真实效果。第二组必须维持同glm-flash-low及完整原四题范围，
以第一组作同模型实测参照，覆盖全部失败、恢复、必要收尾和外层Host成本。

## 第二组实证与第三组前窄修

第二组采用b0c9d25，原完整公开1／隐藏3题及评分不变，全部运行和独立验收仍为
Codex glm-5.3-flash low。初轮独立报告3/4，保留的负面裁决与其自身理由存在矛盾，
不能由粗modeling-quality标签直接推导模型知识缺失；原报告未改写、未归一为PASS。
Delivery已启动r2，仍如实扣账。r2自查另发现真实关系端点方向错误，经原流程授权，
同run实质修模于2026-10-18T19:34:06.658Z开始，计第3轮；总3/3、fresh starts2。
最终r2公开1/1、隐藏3/3独立非盲回归通过，同freeze、治理读回无漂移；不代替复杂业务
验收。两个run CLEANED、四个evaluation owner退出及bootstrap凭据撤回已核验。
完整成本在外层Codex Host复盘退出后再去重汇总，不只计算最后成功轮次。

本组还暴露了可避免的协作／参数往返，第三组前仅作以下差异：

- `team-transport-events.jsonl`的terminal_report_accepted已进入Delivery输入，
  不是来源白名单丢事件。仅将其标量agent映射为agent_id，仍不注入私有report/body。
  Delivery的两处实际指令明确：pending后新的生产角色完成回执触发同freeze、新request
  的readiness检查，不等待额外run-settled信号；实际准入仍由原接口判断。
- Judge每个最终裁决默认用现有完整JSON材料+report_ref，从首次提交保留null／省略层。
  原评分、独立判定、字段校验及不可变性不变；消除“先提交占位裁决以后再改”的误解，
  不自动更正、替换或奖励任何标签。材料输出仅经已有scoped handoff工具，消除旧说明中
  要求发布文件却笼统禁止写文件的冲突。
- T0复核：暂停顺序仍保护issue ledger和当前turn的协作边界；底层ledger也拒绝过早
  resolution，前台重复门不是唯一写入安全保护。保留可恢复顺序反馈，reported时明确
  `issue_pause_pending`、缺失的bound pause和下一动作，并写既有receipt；不自动代发pause。
  flat MCP schema的reason只对abort有意义，pause携带该字段不保护任何硬门，故仅在
  MCP适配层丢弃它。未知字段、resolution字段、内部控制对象、身份／epoch及resume／abort
  保持严格。实际minimal-chain Coordinator与report_issue工具说明补self-reporter同turn pause。
- 外层本地监督器遗漏Delivery已finish/read_only_wait通知，导致已授权收尾延迟。第三组复用
  脚本仅补activity／结果存在性变化通知；普通心跳仍不唤醒模型，不新增平台运行框架。
  Host必须核对实际role消费和pause回执，不以提交或派生状态文字当作成功。

新增角色回执测试先红后绿；本批Delivery输入／唤醒／会话、前台stdin／FIFO、issue、真实
socket恢复、CQ handoff及独立report runtime相关回归333 passed、28 subtests passed。
初次命令含不存在的测试文件，exit4且未执行；修正路径后上述完整选择运行通过。
前批3353项全量证据保留，本批不冒称重新全量。没有backend/frontend改动或应用重启。
GitNexus前台入口upstream LOW（2个依赖），事件投影入口未索引为UNKNOWN，采用直接调用点
与边界回归补证；不宣称完整图影响覆盖。F3/F4仍未实施／未启用，021继续暂停。

审查补齐了Judge实际启动的两处提示（`_CQ_JUDGE_ROLE_INSTRUCTIONS`与acceptance/instructions-v3），
避免旧inline说明覆盖默认材料引用。对应report-reference／acceptance回归86 passed，包含负面
裁决及理由／failure_layer原样保留的新增socket回归；此组与前述333项有交叉，不相加冒充
419个独立测试。两轮选择均exit0。只读审查最终无阻塞；所有实际提示面同步，评分器未变。
