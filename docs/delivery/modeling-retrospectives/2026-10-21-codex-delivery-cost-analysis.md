# Codex GLM low：Delivery 高消耗与停止核查

用户授权停止本轮进程并分析 Delivery 消耗。本次只做生命周期收口、原件分析和验证记录，
没有实施运行代码修复，没有新增建模或模型调用。分析目标是同一最小链任务，不扩成全项目审计。

结论：**重复事件形成旧输入积压，分页补读又扩大历史，而阶段换线程被缺失请求身份阻断。**
Delivery 在长线程中反复解释等待，生产完成后还继续处理旧 provider 恢复输入，最终需要 Host
补位交接。不是主要花在输出答案，也不是仅靠降低 effort 就能解决的问题。

## 范围、停止与结果

- Task/Profile：`r4-3-026-minimal-installation-chain`；Codex／`glm-5.3-flash`／low，
  代码 `1d88669`，独立 Delivery 及生产／验收同预算。
- Session：`minimal-chain-20261020-codex-glm-3cny-171156`；生产 run 为同前缀 `-r1`。
  一轮初建、一次 semantic start；追加金额和同线程恢复没有增加生产启动。
- 用户先授权3元，再追加3元，共6元；不追加或重置原账本。
- 明确 stop 后，两组验收与生产正式退出，源 run 为 `CLEANED`；随后停止绑定 Delivery。
  八个明确绑定的生产／Delivery／验收 PID 均不存在；精确任务路径扫描也无匹配进程。
  四个 Host／验收临时 API key 经数据库读回均已撤销。其他历史任务未停止。
- 模型 revision 2、两个原子应用回执、治理读回、自查和只读交接原件保留。独立验收的
  公开1题／隐藏3题因预算控制及用户停止未完成：两份报告格式／绑定有效，但均无有效裁决，
  `full_pass=false`，不能据此判模型质量失败或语义 PASS。
- 源清理审计仍记 `private_credentials_destroyed=false`；API key 已撤销、源角色
  `auth.json` 已不存在，但不把保留目录中的秘密副本审计冒充零残留，不撤销长期供应商凭据。

原件均在本机 [Host目录](../../../workspaces/minimal-chain-20261020-codex-glm-3cny-171156/)。
停止／撤销证据为 `explicit-stop-final-verification.json`；数值、定位和代码入口见
[证据摘要](../evidence/2026-10-21-codex-delivery-cost-analysis.json)。分析者未参与独立答题或评分。

## 数值：次数与累计历史共同放大

Delivery 原生 rollout 的180个唯一 `response_id` 与同线程累计数值一致；非把累计值逐行相加。
截止最后已留存数值，输入42,143,430，输出52,364，合计 **42,195,794 token**。
其中缓存输入41,202,304、未缓存输入941,126；推理输出2,837已含在输出中。
全链8个已记录线程合计50,056,840，Delivery占 **84.30%**。外层 Host、辅助及缺测失败调用
另列 unknown；不把本地统计当完整账单。复盘自身消耗另计，不混入本次运行链。

| 原生 turn 的实际工具组成 | Turn数 | 响应数 | 输入token |
| --- | ---: | ---: | ---: |
| 仅 `yield_delivery` | 36 | 72 | 12,673,384 |
| 仅补读材料及 `yield_delivery` | 11 | 55 | 17,260,453 |
| 其他，包括启动、审核交接、恢复和控制 | 18 | 53 | 12,209,593 |
| 合计 | 65 | 180 | 42,143,430 |

前两类占输入 **71.03%**，但不能把其中所有必要事件确认、读取都当可删除成本。
唯一线程单次输入从33,666增至458,770，平均234,130，最大458,770；阶段切换实际为0次。
缓存率97.77%只说明多数历史被缓存计价，不能证明累计token降低。

按原冻结价表对已知数值估算，Delivery约1.97462808元；全链已定价数值小计2.74692240元。
预算投影另有暂估5.054630元，合计估算7.80155240元，含在途／控制尾差；**不是已证实
实际扣费7.80元**。不能将暂估全部归给Delivery，或将未计量Host成本记零。

## 已定位原因

### 1. 同一 provider 等待反复记成新决策，暂停期间积压旧输入

`runner.py` 在 provider wait 期间重排未送达消息，每次循环追加 `delivery-deferred`。
本轮9个 delivery_id共9,585条，区间为17:26:09—23:44:16 UTC，detail相同：provider wait
active，需显式恢复。保留重排保障消息最终送达是必要的；每次重排均触发新决策并非必要。

`delivery.py::_is_decision_event_noise` 不识别该类重复状态；`_diagnostic_state` 也未将它
折叠为相同问题状态。因此 `_decision_events` 按每条新字节位置更新chain、产生输入。
观察10,446次、生成165个决策packet，其中123个仅事件链变化。并非全部165次都是无效，
但此处重复状态有确定原件。暂停期间未持续发生模型调用；主要后果是恢复后消化旧队列。

### 2. 分页的“读原件”退回完整 journal packet，补读抵消最小输入投影

`DeliverySession._page_view` 将最小v2视图截成12,000-byte片段，却把 `read_original` 指向
原 `session-events.jsonl` packet。原packet还包括snapshot、fingerprint及累计事件状态。
工具说明又建议优先读该不可变区间。模型照此补读时，重新读回大量不属于当前决策的历史。

实际36次 `read_delivery_artifact` 中31次读session journal，14次重复完全相同的
path/source_ref/selection；还有2次参数／区间失败。可观察到同一input的不同v2分页阶段，
又读一遍相同原区间。23:46—23:53收到的旧页仍包含17:26的provider状态和3元旧授权；
虽附 `current_state` 指向新绑定，但仅为另一个大原件引用，没有消除追读旧包的成本。

这既是当前投影／分页合同问题，也有Agent未优先处理最新绑定的问题，不能只责怪模型重复读。
Host也在首次看到这种积压后才补位，未及时解除旧等待，属于实际兜底成本。

### 3. 配置了阶段短线程，但Delivery自己的缺ID请求阻断切换

配置有production／acceptance边界，`phase_thread_history=[]`。Delivery于17:18:17 UTC
调用 `resolve_issue` 未传request_id，Host账本保留了 `request_id=null`。
`DeliverySession.call_tool` 现有自动身份注入仅覆盖submit_instruction／standby_run／
complete_cq_acceptance，没有覆盖resolve_issue。`_request_projection`把它列为uncorrelated，
`_phase_thread_handoff`据此返回 `request_identity_missing`，生产边界无法切换。

27条已送原生用户输入包含该错误。不能把无ID历史改写成已确认身份，也不能删除写入／
授权保护；本次最窄修复面是遗漏的身份接线及真实旧回执对账，而非另建恢复框架。
这与上一轮“已清理启动失败run缺账本”的已修分支不同，不把旧修复误判回滚。

### 4. 正式拒绝被保留为pending，当前恢复完成却继续等第二组请求

第一组provider恢复于23:43:11、23:44:16 UTC实际清除Modeling／Coordinator等待。
第二组请求于23:44:55提交，被正式拒绝为 `provider_wait_not_pending`。拒绝本身正确。

`_request_projection`仅将 `outcome=accepted` 放入settled，其余全入pending；
`record_observation`显式request_results又仅遍历settled。于是已拒绝请求仍作为“未决”出现，
而不是准确的已结束失败。拒绝信息没有完全丢失：pending.result仍含code和receipt，
但Delivery继续写“恢复请求在途”，没使用这些事实或追到最新状态。

23:44:55—23:53:06窗口49个响应读取18,068,247输入；包含必要事件，不能声称全部可删。
Coordinator已在23:48:07完成正式报告，Delivery仍追读旧页；Host于23:51:58经原接口
完成handoff，得到ready=true、无pending/unknown writes及只读阶段回执。

### 5. 预算控制增加往返，确认失败进一步放大旧线程

金额阈值／迟到用量引发多次pause/resume，原日志保留10次预算控制消息。
Delivery调用11次record_flow_confirmation，5次返回失败：两次参数校验，三次落入
`unified conversation has not been enabled`。其中当前控制ID不匹配会落入conversation
分支；延迟读取旧输入与控制epoch变化构成竞争，不能把它们当业务语义问题。

金额暂停仍直接保护授权，不应删除。低成本修正方向是程序准确确认当前control身份、
区分过期控制回执与没有conversation能力；不让模型通过反复试参数维护暂停存活。

## 旧优化核验与最小建议

| 既有范围 | 本轮判断 | 最小后续处理，尚未实施 |
| --- | --- | --- |
| 030 F1／F2、022 | 代码已采用；重复延后、分页原件回退和旧队列使当前场景效果未达预期 | 先按delivery_id及真实状态折叠重复延后；保留原件，只在新问题／状态变化时唤醒 |
| 030 F3、OPT-20261019-DSH-03 | 配置已启用，实际零切换，当前缺ID子条件待调整 | 复用既有call_identity给resolve_issue补稳定ID；旧请求按真实消费证据对账，不伪造ID或绕过未知写入 |
| 030 F2／F4机械接续 | 正式拒绝及当前生产结果未转成进展，需Host补位 | accepted/rejected均按真实终态投影；拒绝只保留必要异常处理，当前pending应区分“失败已知”与“仍在途” |
| 030 F2／032读取合同 | 补读31次journal、14次精确重复区间；本轮未降耗 | 页续读返回同一v2投影的连续片段；精确保留原件引用供专项查证，避免默认退回整包 |
| 4.4-002金额控制 | 阈值关闭与一组实际暂停有证据；迟到估价、尾差和全员暂停闭环仍PARTIAL | 先修已定位控制身份反馈；金额账、真实暂停、语义验收各自核验，不把新增额度当修复 |

优先处理“重复状态→旧输入积压”和“拒绝终态→误等待”，再修分页与阶段身份；这些都复用
已有观察、回执、分页及线程能力，不新增计数硬门、角色上限、治理层或通用编排框架。
建议尚未获得实施授权，不新增OPT编号。验证应复用本轮脱敏事件／回执做确定性合同回归，
然后仅在另获授权时用同Task、完整原题集及同计量口径实测；不得删题、降评分或将成本转移
给Host后宣称净降耗。F3切换须以实际native线程身份取证。

完整任务已知50.06M，已超过030的10M量化目标；独立语义未完成，整体PARTIAL。
生产应用成功不替代独立验收。纯语义有效时间及Host归属仍unknown，不将6小时暂停或
进程存活当有效建模时间。文档／JSON／本地链接检查仅验证本次记录，不新增运行测试。

## 后续修复

用户随后要求“修复发现的问题”，五处窄修及工程回归见
[修复与验证记录](../records/2026-10-21-delivery-cost-fixes.md)。上述原运行数值、失败与
独立验收缺口保留；未恢复已停止运行，真实token降幅与语义结果仍待后续获准验证。
