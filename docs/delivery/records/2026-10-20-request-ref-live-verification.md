# 完整模型变更请求引用的真实验证（2026-10-20）

**引用输入真实采用成立，本次有界L1独立非盲回归通过；稳定预防及净降耗仍未证明。**
用户在接口修复`2c65731`完成后要求“请继续”，沿原三轮授权的剩余一轮验证。
原r1失败和r2成功均保留；本轮r3初建一次，无验收后实质修模，原额度已用3/3、余0。
没有新增平台实现或变更业务范围。逐调用、材料摘要、实际载入对象、报告绑定、逐线程用量及原件前缀见
[数值与原件导航](../evidence/2026-10-20-request-ref-live-verification.json)。

## 运行范围与结果

- session=`minimal-chain-20261020-request-ref-live`；run=`minimal-chain-20261020-dsh-glm-low-r3`。
  全角色使用DSH、`glm-5.3-flash / low`，Task/Profile沿既有最小安装链，唯一业务来源不变。
- 2026-10-20T01:04:37.586733Z真实semantic start；距本次用户“请继续”约3分21秒。
  以下时点均UTC；新加坡本地为UTC+8。
- project=`20a8e82f-bcf8-443a-a806-269997b46b79`，ontology=`cf0661bb-9a53-40bd-a543-9ae7d2b8a1ba`。
  两批原子application分别于01:07:40Z、01:08:53Z完成，revision 0→1→2。
- 两个owl:Class和一个有向ObjectProperty，未写具名个体或安装实例事实。
  Modeling实际治理读回核对sourceClassId／domain为Installed Asset、targetClassId／range为Service Site；
  association为COMPLETE、3资源、26 statements、0 issues；01:09:57Z写入Session关闭。
- 完整题池经Host对照来源逐点私审，全景／切片分别完成；freeze=`cq-batch-0001`，
  digest=`sha256:1f2dd49e591a350a54c91878edeec230f9927c80e760b0751d226fae773059d1`。
- 原公开1题和隐藏3题均由独立Consumer／Judge实际执行，全部pass／failure_layer=null；
  两组同freeze、同model_binding，未执行题为空、模型与读回复核无漂移。
  Runner于01:18:04.567836Z接受`cq_verdict=pass`，01:18:47.757285Z接受standby。
  semantic-start到验收闭环13分26.98秒，到standby14分10.17秒。
  这是最小链有界L1 non-blind-regression，不扩大为复杂业务、盲测、L2或自主Delivery PASS。

## 引用是否真正避免再次转录

Modeling自行写完整JSON并发布给runner，六次提交全部只传`modeling_id + request_ref`，
没有一次内联request。三份不可变请求的manifest摘要均匹配原件；程序保存的inputs.request
与相应完整原件解析对象逐项相同（包括失败请求），不是根据成功回执推测原样载入。

| 完整原件 | 实际提交与结果 |
| --- | --- |
| `material-a8178b4441db4156bd6440b8a1bdba60/batch1-classes-request.json`，2665 bytes | 同引用四次：范围未确认1次、CQ未冻结2次、成功应用1次；三次未写入反馈后不重写正文 |
| `material-53023d43e8e94593b43c56b0a4e78248/batch2-relation-request.json` | 原件含relation_type不支持的aliases，定位`/changes/0/fields`并可恢复拒绝；无写入 |
| `material-89e2467b45b2472d91c9bc77248fb2d4/batch2-relation-request-r2.json` | Modeling自行修正文并发布新引用，原子应用成功；未由Host代写或平台静默改参 |

因此，本轮补上了“正确原件→确定性执行”的已确认接口缺口，没有重现控制键反复嵌入fields。
引用不保证原件本身合法，也不证明供应商内部重复错写的唯一诱因已定位或稳定一次成功。

## 残余问题与边界

- CQ首次草案字段错误自行纠正，另有一次材料权限拒绝；保留这两类成本，不归因模型语义失败。
- Modeling终态因排队输入拒绝6次，Coordinator另有缺少Modeling终态1次、排队输入1次；
  队列逐条消费后原线程成功，没有重开。新`runtime_input_pending`类别正确定位等待，
  **仍未消除多次终态往返**；未用本次通过关闭原05整体“待调整”。
- 独立Consumer的公开概念题和隐藏方向题内联报告各有两次字段漂移拒绝，随后按现有report_ref
  通路恢复。Consumer／Judge均未生产或修复模型，Host未改裁决或保留证据。
- 状态投影在accepted closure及standby后仍列`cq_acceptance_closure=1`，实际原始回执均为accepted；
  保留该不一致，不盲重放写入或在本轮扩平台修复。
- 本轮无平台修复Host交接，Host完成最小启动、两批CQ私审、持续只读监督与临时凭据收尾；
  这些工作不是业务代答，也不等于无人介入自主交付。语义有效工时占比无精确证据，不能用14分钟
  墙钟或进程存活代替；没有为补该指标扩展harness或新增调用。

## token与成本

统计覆盖全部绑定Delivery线程（实际production／acceptance切换两次，共3线程）、生产及独立验收线程，
全部原生数值响应去重无冲突。input含缓存，output含其原生子项；缺失的cache-write／供应商内部
用量和账单不补零。GLM辅助SSE计量观察器仍按用户此前决定关闭，未为取数恢复。

| 角色 | input | output | 合计token |
| --- | ---: | ---: | ---: |
| Delivery | 6,004,193 | 34,965 | 6,039,158 |
| Coordinator | 951,246 | 14,020 | 965,266 |
| Modeling | 2,035,775 | 14,317 | 2,050,092 |
| CQ | 157,038 | 4,528 | 161,566 |
| 独立Consumer | 348,054 | 6,805 | 354,859 |
| 独立Judge | 458,674 | 3,532 | 462,206 |
| DSH全链 | 9,954,980 | 78,167 | 10,033,147 |
| 当前Codex Host至01:20:23Z | 7,500,786 | 16,435 | 7,517,221 |

本次继续验证的已知input+output下界为**17,550,368**；
Host截止为01:20:23.786Z，之后整理文档／提交／最终答复尾部未含。DSH自身已达10,033,147，
因此10M全任务子目标仍未通过；缓存率或本次单轮完成不代替净降耗证明。
沿原授权累计三轮（包括前两轮已记录的55,959,798）已知下界为
**73,510,166**，未另加前批后续工程／复盘成本及未知尾部。
本轮版本、运行轮数与错误构成不同，不把与旧两轮任务的总量差解释为单因素因果。

## 收尾与验证

新r3、原r2及失败现场、冻结、报告和验收成员保留只读；未收到stop。standby实际接受，
Delivery read_only_wait；Host临时admin/read凭据已撤销（01:19:58Z，私有bootstrap-cleanup.json）。
角色进程保留不代表未完成工作，当前授权余额0；没有未安排的生产／验收待办，不宣称存在额外后台监控。

本次仅真实运行与证据文档追加，没有backend/frontend或Team代码修改；不重复上一提交134项工程测试，
不重启产品服务。文档／JSON／摘要／绑定／链接检查用于证据整理，L1结果来自独立真实报告。
R4.3-025引用输入子项更新为真实采用及本次有界独立语义通过，025整体仍部分验证；
030净降耗与OPT-20261019-DSH-05稳定预防仍未通过／待调整。
