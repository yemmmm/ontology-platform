# R4.3-029 Delivery 职责收敛与宿主交接设计

## 1. 范围与事实基线

权威需求为[R4.3-029](../../requirements/requirements-v4.3.md#r4-3-029)，决策主记录在该条。
代码基线 `7dd96b1`。本轮只细化、设计和独立设计验证，不实现代码或活跃提示，不启动
服务、Provider、建模、修模或真实验收。工作区已有README、复盘、需求登记和演示材料
变更保留；同一需求文件只增改029及其状态索引。

用户本轮明确：**Delivery不负责CQ审核；CQ审核交由宿主。** 宿主指当前获准监督运行的
外层Agent，不是Delivery派生的子Agent，也不是生产Coordinator或独立Consumer／Judge。
宿主审核CQ需要已有明确代审授权；没有授权时交原业务授权人，不因本设计新增代审权。
宿主不参加最终独立裁决，不能从隐藏题／评分点提取生产修复提示。

例子：Consumer没答出“资产属于哪个现场”。Delivery读取报告资格及可披露失败信号，
把公开问题交Coordinator定位；Coordinator请原Modeling检查相关源、候选、实际应用和
读取。若正确关系已应用但合规读取遗漏，Delivery核对请求／版本并交宿主修平台；若关系
未建，按剩余额度修模；若内容已返回但Consumer误答，走独立消费侧重验。HTTP成功
不替代这些证据；隐藏问题只允许传递获准失败信号，不能借例子泄露答案。

## 2. 已有入口与必要差异

| 入口 | 当前事实 | 本需求增量 |
| --- | --- | --- |
| `delivery.py::_is_decision_event_noise`、`record_observation`、`_model_observation`、`_dispatch_observation`、`supervise` | 005／022已分离程序观察和LLM输入，保留变化包、投递基线与分页；除少量噪声源外，新事件仍可能进入决策包 | 原处按§3投影事件，普通工具／消息正文改引用；继续保留未知／坏事件可见性 |
| `agent-packages/delivery/instructions.md`、`skills/delivery/SKILL.md` | 要求Delivery逐点审核CQ、读取答案／公开反馈，且能准备、启动和验证修复 | 改为流程绑定核对；CQ与平台修复转宿主；移除重复语义阅读及新修复执行能力 |
| `delivery.py::DeliverySession.call_tool`、`tool_specs` | Delivery可调用prepare_repair_task／start_repair／verify_repair；repair_completed仅认可自身verification_ids中的效果验证 | 不向新Delivery暴露修复启动／测试能力；宿主直接经Host `resolve_issue`提交正式恢复，保留原严格绑定，不用guidance冒充修复完成 |
| `host_ops.py::submit_cq_review`／`freeze_cq`、`host_ops_mcp.py` | 私有CQ待办含review／question／version／digest，已有审核与冻结入口 | 宿主直接提交审核；Delivery仅看审核完成元数据／回执，再冻结；无需借Judge审核或新增CQ角色 |
| `host_ops.py::resolve_issue`及request ledger／receipts | 已有issue_id、reporter_id、control_epoch及repair_completed字段和恢复回执 | 宿主直接提交；Delivery观察同run回执及issue状态，解决其本地verification_ids限制；不放宽该限制来信任任意文本 |
| `delivery_conversation.py::validate_message` | host_agent与test_answerer均能提供带来源输入；对话有公开投影 | 普通消息只作唤醒／提示，不承载CQ私有正文、平台修复证明；正式结果走Host私有入口及原回执 |
| 通用／minimal-chain Coordinator instructions | 通用包禁止语义审核；精简包已有候选语义检查；两者均无平台能力 | 统一为生产侧语义定位／组织局部深查，不取得最终裁决权或平台写权限 |
| `runner.py::_stage_sources`、`_prepare_handoff_materials`及Task.role_sources | 资料按实际Task角色授权挂载，并非Coordinator全量可读 | 保留挂载边界；先用已有map／handoff，缺源请原Modeling定向补证；必要新增挂载须在原授权内显式配置 |
| `delivery_ops.py`、`delivery_verification.py` | 现有独立repair操作及效果验证已有资源记录 | 宿主可在既有授权内复用；不为迁责删除底层工具或停止历史操作；宿主直接修复也须提供真实测试／运行证据 |

以上是源码与调用点定向核对，不声明GitNexus图覆盖。实施时对实际跨模块变更做影响
分析和代码变更检测；文档设计不要求重建索引。

## 3. 事件与默认输入

保留`delivery-decision-input/v1`、当前状态／changes／coverage／原件引用及原投递确认
方式。不要另设总线、监督角色或摘要模型。以下是对已有事件的**投影规则**，不是要求
生产Agent上报一套新事件名；实施时逐个映射已有来源及字段，未知事件仍提供定位。

| 观察事实 | Delivery默认输入与动作 |
| --- | --- |
| 普通Agent消息、推理、工具成功、数值用量、日志增长、心跳 | 原件留存；不因其变化单独唤醒，不注入正文；阶段状态不变时继续程序观察 |
| scope／scenario-map普通更新、批次应用成功 | 程序保留引用；只有当前阶段推进、依赖解锁或公开反馈准备状态真正改变时唤醒，携带版本／阶段／待办元数据，不传候选全文 |
| 阶段完成、生产handoff-ready／terminal、验收真实报告出现或被拒绝／替换 | 唤醒；给run、阶段、实际工作状态、report资格与scope／freeze／版本引用，缺报告仍未完成；standby不等于无结果 |
| CQ interview／review待办及业务澄清 | 唤醒并保留准确绑定；CQ review交宿主，Delivery不读题目或必答点；业务问题沿原业务输入渠道 |
| 请求失败、未知结果、冲突、权限拒绝、错误参数、issue／控制状态变化 | 唤醒；给准确错误及待处理绑定，原请求／回执引用，未知写入优先；普通参数问题回原调用者 |
| Provider失败、进程退出、流中断、必要存活异常、原件损坏／未知新事件 | 唤醒并给第一异常与确切定位；未知事件不静默丢弃，也不全文注入。必要存活观察沿现有运行器，不新设LLM定时催办 |
| 宿主请求结果、用户控制、授权／额度变化 | 唤醒；保留原来源和顺序，控制优先，重复观察不重放操作 |

“普通成功”只在已知来源、字段和状态语义下折叠；同一响应带错误／不完整／unknown／
待办／终态变化时不能被折叠。不能通过正则扫描业务正文猜完成或异常。语义缺陷由生产
自查／Coordinator issue或独立验收发现，平台程序不解释业务。已接受但无终态的调用仍
保留未决集合与存活观察，不因为没有新文本就认定健康或完成。

默认提供：阶段、授权／轮次余额、未决动作、首阻塞及暂未定位事实、必要版本／报告
资格、宿主待办状态和准确原件引用。022的32KiB分页、16KiB补读、送达基线、pending
完整性及用户控制优先全部复用。Delivery为技术定位按需读请求、参数、回执、版本及
日志；最终只核对独立裁决／分母／资格。公开反馈正文由Coordinator按获准通道读取，
私有Judge依据不需要为Delivery重新解释一遍。

## 4. CQ审核由宿主承接

1. 程序从当前`cq_review`待办提取run／review_id／question_id／content_version／
   content_digest、阶段、未决数量及私有引用，发起§6宿主待办。Delivery只核对这些绑定。
2. 宿主在已委托CQ代审权限内读取当前私有快照、获准源和访谈，逐必答点审查来源、
   业务含义、未知、公共／隐藏可见性和slice范围。起草者自查不算审核；业务歧义交原
   业务授权人，不把测试代答者自动升级为审核者。
3. 宿主直接调用现有`submit_cq_review`，使用真实待办绑定及既有note记录宿主代审、
   授权、依据与决定。`panorama-draft`／`slice-draft`先由CQ改正为正式review阶段；
   不改题池协议，修改题目走原内容修订路径，旧决定不能覆盖新digest。
4. Delivery从原审核回执和待办变化确认全部本次选题的正式审核完成。完成全部既定
   panorama／slice步骤后，Delivery调用原`freeze_cq`，核对真实freeze_id／digest及
   完整选题分母，发生产公开投影和冻结确认。冻结不等于生产完成或语义PASS。
5. 私有题目／答案／来源／审核理由仅在CQ—宿主边界；Delivery的正常输入只含元数据
   与审核决定是否有效。不向生产Coordinator转发审核包，也不取消题目质量审核。

删除Delivery的`submit_cq_review`模型工具暴露，底层Host接口继续供宿主使用。不存在
“Delivery根据宿主自然语言回复重新生成审核意见”的中间语义步骤。022中CQ依据必须
由Delivery阅读的条款在029路径被本节替代；历史人工流程和证据不改写。

## 5. 生产语义定位与故障分流

Coordinator利用当前scenario-map、共享语义决定、候选／应用／读取引用及未决项，
定位受影响slice／概念／关系，派原Modeling局部核对。无需新增完整模型摘要、常驻
诊断角色或全量重读；通用包原“不审核语义”改为“不作最终独立裁决，承担生产定位”。
不默认新增完整ontology-modeling Skill加载；定位方法写入两个实际instructions及紧凑
引用，保留Modeling当前方法。无源权限时请原角色给获准局部证据，不假装读过全源。

| 已有证据／竞争解释 | 下一处理方及最小补证 |
| --- | --- |
| 源有要求，候选遗漏或表达错误 | Coordinator→Modeling；核对相关源、候选及实际交付，实质修模按轮次记账 |
| 候选正确，请求漏项／字段错误 | 原调用者纠正；有参数合同缺陷才交技术路径，不直接归因存储 |
| 成功回执但实际结构与请求不符，执行／存储版本错配 | Delivery核对请求／receipt／actual revision→宿主；保留平台合同嫌疑，不能据HTTP 2xx排除 |
| 实际应用正确，治理读取缺失 | 核对授权、范围、参数、版本、正常过滤及查询完整性；合法读取仍异常才交宿主查投影／缓存／检索 |
| 正确内容已在实际响应，Consumer遗漏／误解 | 独立消费侧重验；不要求Modeling添加已有事实，不把消费失败写成建模质量失败 |
| 题目必答点缺源、错误口径或越范围 | 宿主审查题目；原Judge只裁决冻结证据，修订走新审核／freeze／完整范围重验，原结果保留 |
| 证据缺失／不可披露／读取失败 | 写“尚未定位”、已查内容、竞争解释、具体缺口和下一步；按需补相关层，不要求全角色顺次检查 |

归因仍限四个既有失败层；“尚未定位”是证据状态，不增加第五失败类型。下一处理方
不是责任判决。一般成功写入继续信任回执，不因本表变成逐批强制读回；只在自查、
独立验收或异常定位需要时读取相关部分，保持015／024及应用完整性。

Consumer／Judge不为被验收run诊断并实施修复。需要重新消费／裁决时组织新的独立
验收操作，保留原报告及完整分母，不让已接触生产修复的会话继续冒称独立Judge。
公开失败可原样通过既有公开反馈通道交生产；隐藏失败只交获准信号。无法不泄密地
定位时回到原任务自查，保留未知；不得伪造“脱敏摘要”夹带隐藏答案或对应概念提示。

## 6. 宿主接单、回传和安全恢复

复用当前宿主监督会话及Host工具，不由Delivery启动修复进程／修复子Agent。为消除
“只能用户转述接单”的缺口，在`DeliverySession`增加一个窄工具`request_host_action`：
仅把当前session绑定run的`cq_review`或`platform_repair`请求追加到**已有私有**
`session-events.jsonl`。无新服务、队列、自动修复启动器或任意收件人。

记录包含稳定request_id、session／run、kind、授权引用、当前pending／issue绑定、
预期／实际、受阻步骤、已有源文件引用／digest及定位、已查内容与竞争解释、当前写入
状态。CQ只记录审核身份和私有快照引用，不复制题目。平台交接引用仅含获准技术／
公开生产材料，不含隐藏题／答案／评分理由、完整对话或凭据。同request_id同内容幂等，
冲突给可恢复错误；接单记录不代表修复执行或成功。

宿主`modeling-dev-loop`监督时在现有进度检查中读取该session的新增待办及原Host
pending actions；仅在有动作时处理。挂起时向用户报告“等待宿主处理”，不能假装已有
后台宿主消费者。宿主沿现有本地文件和受限Host入口领取请求，不通过公开对话投送私有
正文。无需新增常驻监听Agent；监督被中断时记录待办，恢复后先对账再执行。

宿主回传：在同一journal用窄宿主侧CLI／函数追加`host_action_result`，绑定原request、
来源、status（completed／blocked／failed）、结果引用及限制；此入口不暴露给Delivery
或test_answerer，也不接受任意外部路径作为可信结果。仅接受当前宿主在session私有
目录保留的结果原件；模型侧`request_host_action`不能写结果事件。来源权限复用现有session本地文件约束。新宿主写入与Delivery共用journal，
两侧追加须使用同一窄文件锁并在锁内取得真实byte_offset，避免跨进程记录交错；
不引入签名服务或第二账本。

- **CQ完成**：结果引用实际Host审核请求／回执；Delivery交叉核对当前digest及待办。
  宿主声称completed而原CQ回执未知／拒绝，仍待处理，不能冻结。
- **平台修复**：宿主按AGENTS先做T0防御复核、最窄修复、相关测试及必要重启／健康
  验证，保存before／after版本和准确验证范围。只有工程检查不等于语义验收。
- **正式issue恢复**：宿主直接调用原Host `resolve_issue(repair_completed)`，携带当前
  issue_id／reporter_id／control_epoch、repair_component、before／after digest、
  verification_reference及必要mutation_reconciliation。Delivery只观察原请求回执与
  issue-control状态变化，不再调用自身受verification_ids限制的repair_completed路径。
  如果过期或证据不足，返回可操作失败，补证后原run继续，不伪装为guidance绕过。
- **非issue阻塞**：Host结果和真实写入／运行状态核对后，由Delivery沿原submit_instruction
  或resume_live_run等适用入口推进受阻步骤；不为每个问题强造issue。普通参数纠正
  沿原调用／guidance即可，不需要宿主修复完成证明。

Host结果只表示宿主动作终态；原恢复请求accepted也不等于模型已恢复成功。Delivery
继续核对当前reporter恢复、所需真实调用／读回及阶段结果。结果通知丢失时先查原
journal／request receipt，不创建新修复或重放写入。缺少Host结果、旧epoch或无法读取
验证原件时保留受影响步骤的阻塞，允许补证；不能将其他安全工作一并永久杀死。

未知写入先用现有`get_request_result`／`reconcile_write_state`及原Attempt／资源回执
核对。运行重启需先确认相应写入／租约安全条件；不得以read health代替写入对账。
优先同run恢复，fresh start及实质修模仍消耗适用授权轮次，本设计不授新额度。

已存在的Delivery repair operation仍保留观察、结果读取、必要停止与清理，不能删掉
所有repair分支导致遗留进程失管。新请求走宿主；不以旧config.repair存在自动授予
新Delivery修复启动权，也不重命名底层Host工具影响其他获准调用者。

## 7. 实施边界和相邻合同

实施时最小改动集合：

1. `delivery.py`原事件投影、默认观察、工具暴露及私有宿主请求／结果的窄接点；
   `delivery_conversation.py`只在确有需要时增加宿主CLI命令接线，不把结果塞入公开消息。
   明确将Host待办／结果状态接入`observe`／`record_observation`；
   `_restore_decision_inputs`从journal重建未决宿主请求与未确认送达结果。投递确认仍沿
   022，不以“已观察／已接单”当已处理；同run已有正式回执可用于中断后对账。
   journal重建／分页复用022，Host结果引用读取限定在当前session。
2. 两套Coordinator instructions、Delivery instructions／skill、宿主
   `skills/modeling-dev-loop/SKILL.md`及`references/team-runbook.md`，更新实际加载的
   CQ审核、语义定位、技术升级、宿主接单和恢复责任，不只改其中一份说明。
3. Host审核／resolve_issue原协议尽量不改；宿主CLI仅复用其入口，不增加修复执行框架。
   现有`delivery_verification.py`可供宿主复用；若直接修复，验证引用依原issue合同落盘，
   不将`effect_verified`设为无条件真。
4. 同步022的“职责不变／Delivery逐题读取”在029路径的继承覆盖说明；005事件去重、
   019成本口径、023权威派单、024／025直接写入及028已有模型感知保持。实施时同步
   Host接口使用文档及工具合同，既有历史设计／报告不倒写为029已实现。

本设计全部选择可以实施；待实现时需机械核对实际事件字段／CLI参数名，不能据此
重新打开CQ归属或加入新的审批门。无需新增业务表、API路由、生产角色、Ontology资源、
模型摘要产物、隐藏答案脱敏算法或Protocol／模型dry-run。

## 8. 验证安排与完成门

| 对应需求 | 工程验证及关键反例 | 后续真实证据 |
| --- | --- | --- |
| A1／A4 | 普通消息／工具成功／心跳不唤醒；阶段／错误／用户控制／存活异常送达；成功响应带unknown不能被吞；busy和接收未知不丢待办 | 实际加载材料及Delivery输入轨迹，不靠prompt文字宣称已减量 |
| A2／A3 | 通用及最小包均可组织语义定位；受限源不扩权；表§5各反例与证据不足状态均覆盖，不把HTTP成功当正确 | 原Coordinator／Modeling局部查证及下一处理方，保留是否实际读过的证据 |
| A5 | 新Delivery无修复启动／测试工具；Host交接绑定、重复／冲突、结果过期／伪造来源／原件不可读可恢复；已有repair可收尾；宿主直接resolve_issue成功且不依赖Delivery.verification_ids | 获准故障中宿主修复、测试／部署、原run恢复；原失败不覆盖、未知写入不重放 |
| A6 | 宿主审核新digest→实际回执→Delivery冻结；未审／拒绝／旧digest禁止冻结；私有题目不进Delivery默认包或生产；冻结原分母不变 | 独立完整公开／隐藏验收；修题不能抹去原失败或缩小题池冒充通过 |
| A7 | 使用019已有采集，按角色和阶段计入补读、宿主CQ／诊断／修复、辅助模型、压缩和重试 | 同范围／模型effort／并行／代码条件对照；非同条件仅报告观察，不补造节省比例 |

工程测试优先扩展`test_delivery_wakeups.py`、`test_delivery_decision_input.py`、
`test_delivery_session.py`、`test_delivery_ops.py`、`test_r3011_cq_lifecycle.py`及
现有加载／source隔离测试。不新建仅匹配一次运行输出的验收器。活跃Skill实施后运行
适用validator；按实际变更范围运行Team及AGENTS要求测试和运行检查。

独立设计验证只检查需求—设计—代码事实的可实施性与边界；后续独立工程验证和获准
真实L0／L1及净效率分别记录。当前未执行A1—A7工程／真实运行，029不能标功能或语义
PASS；不会为了设计验证消耗生产轮次。

## 9. 本轮验证状态

独立Reviewer完整审阅及源码合同核对：**Round 1 PASS，0 Critical／0 High，
关键未决假设：无**。本结论只覆盖设计，不覆盖实现或A1—A7工程／真实语义和效率。
状态同步未改变设计§1—8及需求F／D／A行为合同；记录见[独立设计验证记录](../records/2026-10-16-r4-3-029-design-review-record.md)。
