# 2026-10-20 DSH GLM low 最小链建模及降耗复盘

本轮建模完成：公开1/1、隐藏3/3独立非盲回归通过；授权3轮已用2轮、fresh starts 2，余1轮未用。
Delivery阶段短线程实际切换3次，局部优化已采用；Delivery记录总token较最近同为两轮的任务少33.64%，
但非缓存输入增加91.75%，不能作单因素或净费用结论。**本任务DSH全链34,286,333 token，
加已归属Host至少55,959,798，10M子目标验证未通过。**

原件与逐角色、逐线程、时间及比较身份见[数值证据](../evidence/2026-10-20-dsh-glm-low-retrospective.json)。
本文不改写原模型、冻结、失败记录或独立裁决。后续工程优化未热载到已验收run，不用本轮PASS证明新代码降耗。

## 范围与真实结果

- Task为`r4-3-026-minimal-installation-chain`，Profile为同名`-dsh`版本；Delivery、生产、CQ、
  独立Consumer/Judge均为DSH、`glm-5.3-flash / low`。Host为当前Codex技术会话，另列成本。
- 唯一业务源为`minimal-installation-chain-source-v1`，新项目新scope，保持完整原公开1／隐藏3题，
  原未知口径和评分不变，不引入其他场景真值。当前代码起点`30b22a6`，r2采用提示窄修`c54ff35`。
- r1=`minimal-chain-20261020-dsh-glm-low-r1`：13次原生模型提交均未写入；重复错误字段嵌套经
  原线程正式guidance仍未纠正，安全停止至CLEANED、空scope删除，失败原件保留。
- r2=`minimal-chain-20261020-dsh-glm-low-r2`：4次提交包含2次可恢复拒绝和2次成功原子应用，
  revision 0→2，实际治理读回、端点逐IRI核对和association COMPLETE，写资源关闭及凭据撤销。
  未发生验收后实质修模，不能将分批写入或参数纠错再扣轮。
- 两组报告同`cq-batch-0001`、同freeze digest、同model binding；无未执行题、模型漂移或读回复核漂移。
  Runner于17:18:13Z接受`cq_verdict=pass`，17:18:41Z接受standby。属于有界L1非盲回归，
  不扩大为完整工业场景、L2或自主Delivery PASS。正常四次CQ私审外，还有三项Host技术诊断及多次补位。
- Team、Delivery、验收owner、模型和证据保留只读standby；本轮未收到stop。Host临时admin/read key
  已另行撤销，证明在私有`bootstrap-cleanup.json`。不把待命PID仍存活当作未完成验收。

## 时间与第一失败层

以下均UTC，显示时间加8小时即新加坡／北京时间。台账准备16:49:39Z，第一次真实semantic start
16:50:01Z，相隔22.32秒。该台账起点到standby为29分02秒；第一次semantic start到完整验收为28分11.52秒。

| 实际事件 | 时间 |
| --- | --- |
| r1 semantic start | 16:50:01Z |
| r1安全停止／空scope清理 | 16:59:28Z |
| r2 semantic start | 17:00:19Z |
| r2完整CQ冻结 | 17:03:36Z |
| 两批application | 17:04:03Z、17:04:32Z |
| Modeling正式终态被接受 | 17:09:42Z |
| 生产交接、只读封口 | 17:15:18Z |
| 独立公开／隐藏验收闭环 | 17:18:13Z |
| standby接受 | 17:18:41Z |

关系应用完成到生产交接相隔10分46秒，大头在排队消息、终态、issue及供应商等待；不是缺关系或业务修模。
跨度不等于有效语义工时或CPU，现有原件不足以精确计算有效语义比例。已停止扩平台/harness，只修当前反馈缺口。

| 现象与证据 | 已定位原因／归因 | 处置及边界 |
| --- | --- | --- |
| r1重复`change_schema_mismatch`，13次提交均无batch | `platform-contract`，最窄层是模型原生发参；重建stream参数与tool/call相同，实际schema正确，无桥接移位证据 | 保留正确校验；同线程guidance无效后停止，补权威提示再获准fresh r2。不能据此推导模型语义质量失败 |
| 两轮Coordinator共6次SERVER/HTTP500 | `runtime/infrastructure`，已定位供应商HTTP边界，不能推测内部成因 | 原session恢复，不切模型、不计新轮；不能用提示掩盖上游故障 |
| r2七次真实终态拒绝包含`unconsumed DSH input` | `collaboration/routing`；真实队列尚未消费时守卫有必要，但通用错误同时提unknown，使普通排队被误读为需Host对账 | 重放连续事件，确认无gap/conflict；静默后消费十条输入、终态被接受。未删除守卫或伪造消费 |
| Delivery按`broker_rejection`及`ack=not_applicable`误判能力不适用 | 终态观察器缺少准确类别，ack其实是固定审计字段；需要读原生工具结果才能定位 | 新增窄类别`runtime_input_pending`，同步Runner白名单和Delivery角色投影，减少无必要原件补读／修复请求 |
| Coordinator在Modeling终态已接受后仍报告旧阻塞，后续重复pause误判仍在暂停 | 旧指导排队、供应商500、issue握手交织；拒绝只说“当前状态不合法”，没有实际状态 | 新错误返回受控state；已resolved不再被解释为waiting。保留原CAS、epoch、pause/resume及写入保护 |
| Consumer部分failure_layer与成功读取／完整答案不一致 | 独立Judge已依据真实证据纠正，最终四项均pass/null | 保留原件，不改裁决或降低分母；不据标签自动修模，也不新增让平台判断业务未知的硬门 |
| Host多轮状态阅读和长上下文重复进入请求 | 本任务Host已记录21.67M，明显影响全任务目标 | 将本轮Host成本纳入下界；宿主skill明确优先精确引用／增量摘要／有界工具等待。工程与复盘成本另列 |

## 旧优化是否生效

| 原项 | 本轮实际采用与结论 |
| --- | --- |
| 030 F1／F2、022、OPT-20261019-DSH-02 | v2及程序观察继续采用。Delivery主动get_run_status仅1次，get_request_result 2次；不能继续主要归因为主动轮询。69个仅yield的数值响应累计15,415,553输入，原生turn/end共12次；等待往返与累计历史仍大，不能把全部yield算作可删除 |
| 030 F3、OPT-20261019-DSH-03 | **真实采用成立，整体待调整**：r1 production、r2 production及acceptance共3次native切换、4个线程全部计账；不重启生产或重置额度。r2生产边界到17:08:19Z才切，已承担错误与协作历史。6次submit_instruction全部显式给ID，本轮未触发缺省/null身份路径，不能据此关闭该窄修待实测项 |
| OPT-20261019-DSH-04 | CQ沿实际精简包完成新审核、冻结；本轮未见未授权handoff材料探测。只补本场景正证据，不覆盖其他角色/异常 |
| OPT-20261019-DSH-05 | **待调整**：r1仍出现相同字段返工，r2仍有旧指导、重复终态及Host补位。已成功应用内容未重放，最终正确交付；本次反馈窄修工程通过，后续真实效果待测 |
| OPT-20261019-DSH-01 | 原issue/native恢复可最终对账、issue_wait实际移除；本轮新增重复pause和过期issue理解缺口已窄修。自主交付与全部异常不关闭 |
| OPT-20261019-DSH-06 | 13次read_delivery_artifact结果全部成功，完整引用读取在本轮有采用正证据；不以此关闭未触发的内容变更/权限反例 |
| OPT-20261019-DSH-07 | 本轮独立验收均通过，未触发只读retry_of；保持已实现待实测，不以fresh r2冒充只读重验 |

F4仍未实施，021仍暂停；本次不扩大到机械编排实现，也不恢复已暂停功能。

## token口径与比较

input已包含缓存；reasoning、compaction是原总量子集，不重复相加。缺失cache-write／供应商内部工作和账单保持unknown。
GLM额外SSE计量观察器继续遵守原用户删除决定，不为本次取数恢复它。

| 角色 | 原生响应数 | input | output | 合计token |
| --- | ---: | ---: | ---: | ---: |
| Delivery | 144 | 27,614,556 | 53,676 | 27,668,232 |
| Coordinator | 75 | 2,157,385 | 32,836 | 2,190,221 |
| Modeling | 83 | 3,322,536 | 30,058 | 3,352,594 |
| CQ | 30 | 349,374 | 7,403 | 356,777 |
| 独立Consumer | 13 | 199,014 | 3,877 | 202,891 |
| 独立Judge | 14 | 512,071 | 3,547 | 515,618 |
| DSH全链 | 359 | 34,154,936 | 131,397 | 34,286,333 |
| 当前Codex Host，至17:18:24Z数值回执 | — | 21,628,088 | 45,377 | 21,673,465 |
| 本任务已知下界 | — | — | — | **55,959,798** |

Host截止点略早于17:18:41Z的standby，后续必要收尾尾部没有补零；该下界本身已足以判10M未达。
17:18:24Z以后至17:30:53Z的复盘／研发Host增量另有9,916,541 token，后续记录／最终答复尾部未含；
不从任务成本中扣除失败，也不把研发成本隐藏为运行收益。数值原件无去重冲突。

对比最近`minimal-chain-20261019-dsh-glm-low-140728`两轮任务：

| 指标 | 前组保留数值 | 本组 | 观察变化 |
| --- | ---: | ---: | ---: |
| Delivery input+output | 41,694,371 | 27,668,232 | -33.64% |
| Delivery input | 41,644,343 | 27,614,556 | -33.69% |
| Delivery非缓存input | 627,063 | 1,202,396 | +91.75% |
| Delivery响应数 | 139 | 144 | +3.60% |
| DSH全链input+output | 50,528,487 | 34,286,333 | -32.14% |

两组同最小链、同模型/effort、同四题范围且均两次fresh starts，但代码、供应商错误和Host补位不同，
前组Host未完整归属；**只能说局部采用和记录总量观察下降，不能断言单项因果、全任务净收益或费用下降。**
本组四个Delivery线程input分别为2,354,914、17,220,418、6,677,246、1,361,978；全部保留。

## 本次已完成的优化及验证

用户在运行中明确授权完成后复盘并实施新识别优化。沿原OPT-20261019-DSH-01／05及
R4.3-022／029／030／031／032，完成输入等待反馈、报告事件定位、issue状态反馈及权威提示窄修，
见[实施和测试记录](../records/2026-10-20-modeling-feedback-optimization-record.md)。没有新增产品需求或额外建模启动。

最终相关560 passed、2 skipped、7 subtests passed；两项是未启用真实Codex边界探测，不能算通过。
其余修改Python的Ruff、两项skill校验及diff／链接检查通过；Runner完整Ruff保留7项原有问题，
与HEAD逐项一致，没有新增，不夹带清理。新反馈代码只完成工程验证，**真实采用／节省token待下轮获准运行验证**。
当前模型L1 PASS、030整条部分实现／部分验证、10M子目标未通过、自主Delivery未证实分别保留。
