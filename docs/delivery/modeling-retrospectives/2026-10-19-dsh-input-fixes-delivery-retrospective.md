# DSH GLM low 本轮 Delivery 降耗采用复盘

结论：不是整套优化没有接入。v2增量输入、完整source_ref、直接新回执与减少主动查询
已有本轮采用证据；**F3阶段换线程没有实际执行、CQ材料纠错改错提示面、共用诊断去重
没有覆盖嵌套DSH工具错误**。另有真实的DSH恢复状态派生缺陷，误导Delivery重试已经
解决的issue。错误与排队协作增加往返，同一长会话又反复携带所有历史，二者相乘。
降耗目标本轮未达到，不能因独立语义通过或高缓存率称优化成功。

本次用户要求分析原因；仅保留证据、离线分析与文档状态更新，不实施建议、不发模型请求、
不控制保留run、不消耗剩余轮次、不重判原独立语义报告。

## 范围与数值

本轮 `minimal-chain-20261019-dsh-input-fixes-r1`，代码`9945ea2`，全部角色DSH /
glm-5.3-flash / low，原最小安装链、公开1题／隐藏3题，初建1/3轮；模型rev7，独立
非盲回归4/4通过，已只读standby。读取原snapshot、native wire、journal、角色实际
instructions及原报告。原始记录位于同名`workspaces/`、Delivery session及`.delivery-ops/`。
共享数值依据见[分析证据](../evidence/2026-10-19-dsh-input-fixes-delivery-analysis.json)。

| Delivery指标 | 上轮共用唤醒防护组 | 本轮输入修复组 |
| --- | ---: | ---: |
| 原生数值响应 | 68 | 117 |
| 累计输入 | 12,014,191 | 27,786,274 |
| 输出 | 16,487 | 27,478 |
| 非缓存输入 | 631,599 | 967,010 |
| 单次平均输入 | 176,679 | 237,490 |
| 最大单次输入 | 317,967 | 481,894 |
| 原件读取／失败 | 15／12 | 10／1 |
| get_pending_actions | 5 | 1 |
| get_request_result | 7 | 3 |
| yield_delivery原生调用 | 13 | 58 |

累计输入增加131.28%，可描述为响应数增加72.06%与平均输入增加34.42%的乘积；不是
对两种因素的独立因果分配。本轮第一次输入24,930，最后一次481,894，未压缩、未切线程。
58次响应只调用yield_delivery，对应累计输入13,684,357，占Delivery输入49.25%；这是
这些响应所带历史的实数，**不是可直接删除的token估算**。56次yield登记成功，另2次
input_id绑定错误；原生turn/end为18，不能把每次工具成功当成推理已经结束。

两组模型、effort、材料与题目范围相同，但故障、授权细节、GLM额外采集开关不同；
这里只比较观察量，不能把全部增量归因于某项修复。Host原运行另有输入16,049,989、
输出27,750；当前分析开销不混入原任务。DSH的cache-write／reasoning和账单仍未知。

## 关联需求与旧优化采用

| 归属与旧方向 | 本轮核对 | 结论 |
| --- | --- | --- |
| 030 F1程序等待 | 已yield，但原生错误及协作变化持续送达；58个仅yield响应、18个turn结束 | 机制采用，减少反复等待推理的目标未达，待调整 |
| 022／030 F2最小输入 | 实际99个v2包，97个不同input_id；1个bootstrap、98个changes；平均10,164 bytes，新回执request_results实际存在 | 已采用；单包有界不限制整线程累计历史，不能关闭净效果 |
| 029／030读取纠错 | 10次读取中9次成功，全部携带byte_length；上轮缺字段12次返工未重现 | 该缺字段子项有正证据；剩余1次为相对路径identity不一致，另案定位 |
| 030新回执与减少查询 | pending查询5→1、request-result查询7→3；不是完全无查询，也不应全禁 | 局部采用；总响应仍增加 |
| 030 F3阶段短线程 | Host配置production/acceptance；实际instructions和工具schema均含thread_boundary，instructions hash与冻结baseline一致；56个成功yield无一个携带thread_boundary；phase_thread_history为空 | **真实采用未发生**；不是模型配置不支持，不能称线程切换已生效或安全检查拒绝了切换 |
| CQ材料通道纠错 | 通用competency-question说明已改；本轮minimal-chain-competency-question明确替代通用包，required_skills为空；实际instructions缺该纠错 | **未进入实际提示面**；保留材料越权重试 |
| 共用问题状态防护／032 | 已移除GLM额外采集，旧纯计量告警风暴未重现；但重复native工具错误仍全部作为变化 | 旧顶层计量诊断正证据保留，嵌套native错误范围待调整 |
| 030 F4机械连续动作 | 本轮仍是freeze/notify、handoff/evaluate等单步调用；未实现F4 | 无本项降耗收益，不能视为实现回归 |
| 019／034／036 | 原生数值持续保留，只有一个Delivery native session，无新旧线程漏账 | 原生统计可复算；跨线程真实采用、账单仍未证明 |

030整条保持部分实现／部分验证，F1/F2综合实际降耗本轮未达预期；F3保留工程通过，
明确本轮未采用；032增加本轮DSH最小链独立非盲4/4正证据，净效率未通过。

## 已定位原因

### 1. 长会话累积未被F3截断

配置不是执行。实际初始v2 task_context已传production/acceptance，冻结native
instructions与工具schema也包含对应能力；但模型每次只填phase/waiting_for/
active_decisions等，没有提交thread_boundary。`DeliverySession.maybe_switch_phase_thread`
首先检查last_yield.thread_boundary.phase，因此本轮根本没有进入切换申请路径，
不能再猜测是未知写入、pending输入等后续守卫挡住。当前源码是可选申请合同，非自动
阶段切换；没有证据说明所有安全条件在每个时点都已满足，也没有可核验的节省量。

验收与收口窗口（生产handoff accepted之后）的22个响应又累计9,544,481输入，
占Delivery输入34.35%。这一窗口仍带生产、参数重试与恢复历史，说明自然阶段边界
是具体优化机会；该窗口全部输入不等于切线程后可节省输入。

### 2. 共用问题去重未理解嵌套native工具错误

实际v2变化中，有49次只包含run.events变化且无新request_results，不能因此全判噪声：
其中有真实错误、实际终态及写入回执，必须保留必要决策。需收窄的是相同问题状态的重复。

离线逐条对回原始字节，37个送达的dsh-wire事件包含25个tool/result、9个初始化／
工具列表成功RPC回执、3个request/header。其中相同的材料错误有两种native表示，
分别重复3次、4次；相同unconsumed DSH input错误重复11次。

`delivery._diagnostic_state`只识别当前data的直接诊断键或可递归识别的结构；这些
native回执把错误放在frame.params.event.data.message.content的字符串或isError中，
未成为该函数的diagnostic。顶层volatile删除也未删除嵌套seq/time/toolCallId等身份。
对原事件调用当前纯函数，以上各组每条都产生不同签名（3/4/11），未折叠同一问题。
这说明旧防护对顶层用量告警有效，**不能据此宣称所有DSH重复错误已覆盖**。
未知诊断、业务变化、真实权限／写入／控制绑定仍应保留；不建议整体过滤native错误。

3个request/header另有相反的误判：原生常规事件识别函数本来会折叠它们，但先执行的
递归_event_needs_action把header.tools[*].parameters.properties.error的参数声明
当成真实error。三条均在该schema路径命中，而非运行异常。修正应识别原生回执的
实际诊断位置，不能递归把工具／业务schema里的同名字段全当运行错误。

### 3. 已恢复issue被Host摘要继续判为待修复

原issue-control于04:42:22.141011Z记录recovery-effective，含实际claimed native
dispatch；Runner已经mark_issue_dispatch并将真实账本置为resolved。Host派生函数
`host_ops._issue_pending`只把无event字段的action=resume/abort当终态，忽略DSH的
recovery-effective。故后续get_run_status仍显示issue_wait并提供resolve_issue动作。

Delivery于04:44:56重复resolve同一issue，被invalid_outer_input拒绝，继而增加
查询、再次Host交接和等待，直到宿主解释真实恢复证据。责任面是状态读取合同／实现，
不是模型业务质量，也不能简单责怪Delivery不理解彼此矛盾的状态。

按响应结束时间分段（UTC）：

| 窗口 | 响应数 | 累计输入 |
| --- | ---: | ---: |
| issue报告之前 | 35 | 3,592,681 |
| issue报告至实际恢复 | 32 | 6,478,726 |
| 恢复至生产handoff | 28 | 8,170,386 |
| 验收与收口 | 22 | 9,544,481 |

窗口量包含共享历史、正常工作与等待，不是对应缺陷的纯成本或可删除成本。

### 4. CQ纠错遗漏实际精简包

前次修复只进入`agent-packages/competency-question/instructions.md`，其中明确
禁止猜材料身份和重复material_forbidden。本轮Profile选择minimal-chain包；其说明
明确替代通用manual/skill，package.required_skills=[]，实际DSH instructions中也
没有新增条款。因而工程上改过通用提示不等于此Task真正加载修复。这是prompt-contract
交付范围缺口。当前材料越权回执应保持准确，不能放宽权限修复重复尝试。

### 5. 上游参数返工与排队消息放大，宿主补位也有成本

原Modeling连续构造相同错误的changes.fields，将自身序列化问题误报为桥接注入；
期间创建并随后删除两个越出源材料的诊断探针。原始tool/call字符串和纯编译器对照
已证明错误键由Agent生成，不是bridge加字段。恢复消息04:35:01提交，直到04:42:22
才被claim，原因是原next-turn队列和长活动尚未处理到该消息，不能称消息丢失。

Host与Delivery多次技术纠错经Coordinator转发，旧消息排队后继续产生重复澄清；
原Team终态报告又遇到11次unconsumed-input拒绝，放大Delivery观察与等待。
原有“不允许未消费输入被终态跳过”保护真实输入完整性；本轮有可恢复反馈且最终已消费，
不建议删守卫、加重试硬上限或重建编排。应减少上游错误与已过时的重复指导，并让相同
问题状态仅在必要变化时交Delivery。宿主自己的补位不是免费优化，应计入全任务成本。

### 6. 原件读取修复大体采用，尚有一次身份路径不一致

本轮全部10次read_delivery_artifact都携带byte_length；唯一artifact_changed使用
source_ref.path=相对host-results路径，实际受控文件已解析成绝对路径。
`_selected_artifact`按原字符串与解析路径比较，故即使byte_length=730及digest均
相同仍拒绝。下一次按返回的绝对source_ref读取即成功；无文件内容漂移证据。
这是私有Host结果引用与读取identity的路径合同不一致，不能归因旧缺byte_length未修。

## 最小调整顺序与验证

以下是建议，用户尚未授权实施，不登记为新确认需求、不启动新模型任务。

1. 先纠正真实状态：Host派生等待识别绑定原issue/epoch/native消费的recovery-effective，
   保留recovery-submitted为待处理；不让已解决issue继续产生待修复动作。
2. 沿共用事件投影识别原native工具回执的诊断状态，区分问题签名与嵌套调用身份，
   同一错误只在首次、实际内容／绑定改变、恢复和复发时送达；未知及保护性绑定保持。
   对普通初始化／工具列表成功RPC回执复用已知成功状态，避免无意义首次唤醒。
3. 把F3从静态可选提示落实到当前真实阶段决策：在原最小输入明确提示已就绪的获准
   边界与原request身份，让Delivery在原yield填写有效交接；继续复用原程序安全判断。
   不另加线程数、尝试次数或固定token硬门，不宣称缺申请等同安全条件已满足。
4. 同步真正被本轮Profile加载的精简CQ提示，复用原材料纠错说明；修正受控Host结果
   path引用身份，使复制完整引用即可读取，不能放宽私有路径权限或内容digest校验。

验证先复用本轮原件离线反例：DSH恢复submitted/effective不同状态；同错误不同native
seq/callId、错误改变／恢复／复发及写入控制绑定；精简包实际装配；完整source_ref读取。
F3仍须真实模型产生thread_boundary并看到新native session及全线程用量，且原四题
独立验收不退步。没有下一次真实运行就不能证明提示采用、线程收益或净成本下降。
F4另按已确认范围分项实施，不将尚未实现的能力混入本轮解释。

## 本次记录变更

029／030／022／032更新本轮部分采用、实际未采用与待调整边界；019／034／036保持
缺值及真实跨线程待证，021继续暂停。仅追加关联需求和既有优化台账，不覆盖旧实测正
证据。未改产品／Runner／角色提示代码，无服务重启、工程套件或新建模／验收运行。
