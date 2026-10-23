# 151612 最小链流程复盘与 R4.3-003 实际效果核对

复盘日期：2026-10-23；被复盘运行发生于2026-10-22。本文只读核对保留原件，更新
需求验证及既有优化项；没有恢复生产、追加金额、调用模型、改动原题池或重新裁决。

## 结论与范围

**R4.3-003 部分生效、保持部分验证。** 本轮实际采用了两处确定性引用：关系端点消费
第一批真实 applied item 引用；最终关联检查由程序直接读取本 run 保留的治理响应。
但三次提交全部使用内联 `request`，没有采用完整 `request_ref`；一个1,799字节的
请求在未写入拒绝后完整重复。真实多页、缺页、引用失效及归属于003的净token效果未证。
不能以工具存在、工程通过或本轮语义PASS关闭整条需求，也不把合法短请求的内联形式
判成模型正确性失败。

运行身份：`minimal-chain-20261022-codex-glm-low-3cny-151612-r1`，代码`99255a3`，
通用`unified-modeling` Profile＋`r4-3-026-minimal-installation-chain` Task，全部托管角色
Codex／`glm-5.3-flash`／low。独立3元金额预算，初建1轮、fresh semantic-start 1次，
没有实质修模。当前024／025路径由Modeling直接提交，不要求旧Protocol翻译或模型dry-run；
本轮不触发旧批准计划入口，不撤销其已有工程及历史真实采用结论。

原有独立非盲回归公开1/1、隐藏3/3全部通过，同freeze／model binding；9条治理读取
复核无drift／unavailable。原验收者与生产隔离，本复盘者仅核对原报告资格，不充当新裁决者。

## 关联需求验证

| 需求 | 本轮实际证据 | 结论与缺口 |
| --- | --- | --- |
| R4.3-003 | 两个真实回执端点引用；ID参数驱动的完整单页关联扫描；整包引用0/3 | **部分验证**；未证明多页、缺页、引用失效及整体重复转录／token减少 |
| R4.3-024／025／026 | 2批原子application至revision2，治理自查、关联检查、独立4/4 | 追加当前最小链有界非盲L1通过；其他变更、复杂业务、L2／L3不由本轮关闭 |
| R4.3-013 | 4,853字节Modeling原件按接收方发布，Coordinator完整读取相同摘要原文 | 局部真实采用；跨错误接收方引用先被拒绝，目录等完整范围及净效率仍待证 |
| R4.3-029 | Host私审后由Delivery冻结、交接、组织两组验收、完成回交与finish | 本轮必要阶段推进未需Host技术补位；仍有过早交接、等待已拒请求及终态措辞偏差，整体不提升为全部通过 |
| R4.3-019／030 | 已知托管14,737,889 token，Delivery9,549,480；原始计量覆盖PARTIAL | 10M子目标未达到；本轮不作003或其他单因素净降耗结论 |

## R4.3-003 的实际采用与未覆盖项

### 1. 真实应用身份引用有效

首批创建请求顺序为Service Site、Installed Asset，原始applied receipt item顺序却是
Installed Asset、Service Site。工具返回的`existing_resource_ref`按真实item身份绑定：
关系`source_class_id`引用`/structuredContent/data/items/0`，`target_class_id`引用
`/structuredContent/data/items/1`，均指向首批保留回执。第二批关系实际应用成功，后续
治理读取和独立验收确认方向与含义正确；没有通过猜UUID、猜namespace或新增property-list
查询重建身份。

这满足既有`RETRO-20261013-06`在当前直接提交路径的预期，记为**局部已关闭**；
不据此关闭003，也不补称已验证旧历史计划／跨角色编译的所有路径。

原件：本run的`evidence/app-server-events.jsonl:6730`（首批结果及真实item引用）、
`:7295`（关系请求及成功结果）；首批回执为
`evidence/platform-responses/b2b1a99b16c073d8ee454a21e6bc4ef1fc6f286d6e33948e00517942ab8366fc-fdef00b695e38a34ffaeaf562d426d2b4783b4d614e9e593753aea77ac4a3a0b.json`。

### 2. 关联检查的确定性搬运有效，但只有一页

Modeling实际调用`modeling_inspect_associations({"modeling_id":"modeling"})`，紧凑JSON
参数为26字节。程序沿`runner.py::_inspect_direct_modeling_associations`执行治理读取、
收集`read_refs`及最终复读引用，再交给`acceptance.py::protocol_inspect_associations`
校验本run观察身份／响应摘要并扫描；没有让Agent再次输入整份bindings。

本次单页21条statement的紧凑原始bindings为10,798字节，完整保留响应文件11,360字节。
结果为`COMPLETE`、`coverage=complete`、3个资源、0 issues／candidates／unresolved，
`semantic_verdict=not_evaluated`。最后一项保持机械检查与独立语义判定的边界。

这证明**该次检查输入面省去了原始结果的再次转录**，不表示净省10,798字节上下文或
相应token：业务自查所需读取仍发生，程序查询、回执、关联摘要及工具描述也有成本。
真实分页没有触发，不能把一页完整当作多页完整、缺页保持PARTIAL或失效引用拒绝的证明。
这些边界只保留既有工程测试结论，本轮没有追加模型或重跑测试来制造真实采用证据。

原件：`evidence/app-server-events.jsonl:7632`及该结果的`read_refs`／`final_read_ref`；
原受治理响应为
`evidence/platform-responses/cc60fbea25ae94d26f7378dc4ca22e4187ab2b1f14a7fb4ee11838ba5e6bb5dd-5b8468e4d7a6e2eafbb37cb5a29eb044db2e5f7f7a0fd8f342a37d0b0620311d.json`。

### 3. 整包引用未稳定采用，不能判净搬运目标通过

| 调用 | 形式／紧凑参数字节 | 完整request字节 | 实际结果 |
| --- | --- | ---: | --- |
| 首次概念创建，原件`:2654` | 内联request，1,836 | 1,799 | `scope_binding_required`，not_written，零Batch |
| 原概念请求重试，`:6730` | 内联request，1,836 | 1,799 | 原子应用成功 |
| 依赖关系创建，`:7295` | 内联request，1,534 | 1,497 | 消费真实item引用后原子应用成功 |

前两次request规范化SHA-256相同，均为
`7f7bfd653dac6c8031c568299b2c4991e955f520ea5d001aebee260d4d536c4b`，
因此确有1,799字节请求正文重复。此前“prepared／staged”只证明内容已准备，不证明已发布
完整请求引用；本轮提交前没有相应`write_handoff_output`／`publish_handoff_material`。
Modeling第一次写文件发生于最终总结交接，不能倒推成提交时用了`request_ref`。

已核对本轮baseline manifest：Runner、能力schema、direct submission及Modeling指令摘要
与当前`99255a3`文件一致。实际加载指令已经说明准备好的完整请求可按`request_ref`提交，
同时保留新短请求内联合法性。不能把当前未采用解释成能力未实现或进程仍加载旧指令。

首个拒绝的源码原因也已定位：scope gate抛`SubmissionInputError`；现有`correction.request_ref`
只在`ModelChangeCompilationError`分支生成，所以这次返回没有可直接复用的纠错引用。
拒绝准确、可恢复，Team修复拓扑后沿同run成功；没有未知写入或不可恢复死锁。
这解释现成纠错引用为何没有出现，**不证明Agent无法主动发布请求，也不证明强制增加
写文件／发布步骤对这个1.8KB短请求一定更便宜**。

紧邻134133轮的两次成功提交确实用了`request_ref`，紧凑参数分别141／153字节；本轮
成功提交却回到内联。只能判引用采用尚不稳定。两轮请求正文和其他实现不同，旧轮原截止
还未完成Delivery收尾，不能把整体token／时间变化归给003或将上述参数差额当净token收益。

## 流程时间与成本

下列时刻均为2026-10-22新加坡时间；阶段间隔含推理、调用、协作和等待，不是有效语义工时。

| 事件 | 时刻 | 含义 |
| --- | --- | --- |
| 新任务授权登记 | 23:16:12.095 | 本任务计时起点；旧任务清理另计 |
| 真实semantic start | 23:17:54.876 | 授权登记后1分42.78秒 |
| 完整题池冻结 | 23:23:15.292 | 公开／隐藏全景及切片审核完成 |
| 第一／第二批应用证明 | 23:24:19.809／23:25:03.121 | revision0→1→2 |
| Modeling资源关闭 | 23:26:15.771 | 关联检查后关闭自身Session／Lease |
| 生产交接接受 | 23:29:04.122 | 写入排空并进入独立验收阶段 |
| 验收完成登记 | 23:32:31.399 | `attempt-0001`、`cq_verdict=pass` |
| finish_delivery返回 | 23:33:21.035 | **从授权登记起17分08.94秒**；真实activity为read_only_wait |
| 上次用量统计截止 | 23:34:53.262 | **18分41.17秒是统计窗口**，不是实际finish用时 |

本轮finish的原始返回为`ok=true`、`activity=read_only_wait`、`pending_owners=[]`；
语义结果、写入封口和原会话保留已有证据，不以整个进程生命周期计算执行耗时，也不强制
把read_only_wait改成standby。Delivery业务文字称“进入standby”不够准确，应沿原返回展示。

| 角色 | 输入token | 输出token | 输入＋输出 |
| --- | ---: | ---: | ---: |
| Delivery（3线程） | 9,523,636 | 25,844 | 9,549,480 |
| Coordinator | 1,742,620 | 9,538 | 1,752,158 |
| Modeling | 1,865,546 | 10,932 | 1,876,478 |
| CQ | 488,609 | 4,691 | 493,300 |
| Judge／acceptance | 800,453 | 3,093 | 803,546 |
| Consumer／platform-examiner | 260,091 | 2,836 | 262,927 |
| 已知小计 | 14,680,955 | 56,934 | 14,737,889 |

截至原23:34:53统计；Host未知且单列、不计任务金额或预算，辅助／迟到／绑定歧义及尾差
仍PARTIAL。缓存输入和推理输出不重复相加。完整有效分类工时未知，不能推算语义占比或
可删除等待。原23:36:43预算观察约计1.43134236元，其中已计价1.24595436元、暂估
0.185388元，余估1.56865764元；是冻结价表估算而非供应商账单。

## 已识别返工及最窄归因

本轮共有15次原生MCP调用终态failed，另有1次提交工具成功返回not_written；两者不能
混成16次平台故障。下表覆盖实际观察的失败及纠正，不用它们推导模型质量失败。

| 现象／原件行号 | 已定位原因及责任面 | 本轮实际纠正／影响 |
| --- | --- | --- |
| Modeling两次消息参数拒绝，`:1952／2002` | 把接收消息里的`work_request_ref`作为发送参数，并传成字符串；发送schema只接受对象`work_request`。collaboration/routing，调用方合同使用 | 移除非法字段后`:2142`发送成功；不需要新增工具或放宽schema |
| scope未就绪，`:2654` | Modeling过早写入；实际拓扑工件尚未就绪。platform-contract前置反馈正确，非模型质量 | Coordinator纠正`topology_decision_ref`后冻结再提交；1次零写入拒绝及正文重复 |
| Coordinator feedback／reply拒绝，`:3235／3836／4757／5077` | 原requester冒充assignee feedback，或把已消费／非活动原请求作为reply槽。collaboration/routing，身份和依赖使用错误 | 改用正常单向消息后同目标继续；没有新建run或扩大通信边 |
| 材料引用通道错误，`:3032／7841／8719` | 占位引用、给Runner发布的引用发给Coordinator、Coordinator把只给自身的外来引用再交Runner；接收方授权校验正确 | 去占位；按实际接收方重新发布；最终Coordinator只交自己的Runner总结，原Modeling已另行向Runner交付，无需再转录原文 |
| CQ三次入口拒绝，`:4019／4150／4308` | 猜错MCP server并尝试Profile未授权的Coordinator／issue通道。collaboration/routing，角色入口使用错误 | 原Runner的cq-slices-approved阶段通知到达后继续；不应为此开放私有CQ通道 |
| work card一次拒绝，`:7982` | 可选文本字段`waiting_note`传null。collaboration/routing，调用方schema使用 | 改成文本后卡片登记；局部参数纠错，不需新防御层 |
| 公开Consumer发布两次失败，`:9468／9528` | 文件配目录members、然后相对source_path无授权映射。collaboration/routing，材料调用参数 | 使用实际授权目录＋文件member后`:9708`成功，最终独立报告有效；未改评分或题目 |
| Delivery三次yield拒绝 | 1次等待身份误绑Host request，2次继续等待已拒handoff；现有准确拒绝有效 | 35次调用、32次登记；转等真实生产终态后继续，非35个独立有效等待 |
| 第一次交接被拒，原请求cq-handoff-0002 | 生产角色交付未全部结算即申请；返回cq_production_pending。platform-contract检查必要且可恢复 | 原新request_id重试成功；不能为提速删掉生产交付／写入排空检查 |
| 两次验收启动参数拒绝 | model_handoff使用相对仓库根的错误路径；存在性检查正确。platform-contract输入使用错误 | 同operation身份换成Runner发布绝对路径，约8秒后两组正常启动，无重复模型执行 |
| finish文字称standby | 原始成功返回是read_only_wait；流程结果与进程状态措辞混淆 | 保留真实状态；不按措辞增加强制状态转换或停止新团队 |

前七组行号均来自本run的`evidence/app-server-events.jsonl`。Delivery部分由原生
function_call／function_call_output及Runner原请求回执配对，详见私有数值原件。
这些纠错最终在原流程恢复；没有证据把所有间隔折算成可删分钟数。

## 既有优化更新及后续建议

1. `RETRO-20261013-06`在当前直接提交身份复用范围局部关闭，保留旧历史；
   `ISSUE-V4-006`原批准计划引用的局部关闭不变，本轮未走该入口。
2. R4.3-003继续部分验证，R4.3-013继续待实测（局部已采用）；不以接收方最终可读
   掩盖前面的错误通道返工。没有新建未经用户确认的优化编号。
3. 后续优先纠正已有参数／材料通道的使用：使用真实接收方发布回执、原活动reply身份和
   当前Runner交接路径；复用已有工具及简短权威示例，不增加角色、传输框架或放宽权限。
4. 完整请求已有引用时复用该引用；新短请求继续允许内联。对scope／CQ前置拒绝缺少
   correction引用的问题，若要实施，应只评估复用现有纠错引用分支的必要差异，并比较
   保留／发布成本与重复转录成本；本轮不把为1.8KB请求强制增加三次工具调用作为结论。
5. 003剩余验证优先放在下一次另获授权且实际存在多页／较大完整请求的任务中，核对完整性、
   引用反馈、实际输入输出与独立语义；本次不追加运行，也不将这些场景前置成所有建模硬门。

## 原件导航与本次检查

- [数值及定位汇总](../../../workspaces/minimal-chain-20261022-codex-glm-low-3cny-151612/retrospective-r43003-evidence.json)
- [选定Modeling原始工具参数／结果](../../../workspaces/minimal-chain-20261022-codex-glm-low-3cny-151612/r43003-selected-calls.json)
- [流程错误及完整交接读取](../../../workspaces/minimal-chain-20261022-codex-glm-low-3cny-151612/r43003-error-audit.json)
- [Delivery原始收尾及失败回执](../../../workspaces/minimal-chain-20261022-codex-glm-low-3cny-151612/retrospective-delivery-closure.json)
- [原运行汇总与独立报告链接](../../../workspaces/minimal-chain-20261022-codex-glm-low-3cny-151612/result-summary.md)
- [权威需求](../../requirements/requirements-v4.3.md#r43-003-确定性产物按引用交给工具处理)
- [优化台账](optimization-tracker.md)

本次仅修改复盘文档及003／原06的验证记录，保留需求和台账已有未提交修改。完成本次
新增链接、数值／摘要绑定及差异格式核对；没有修改产品代码，不运行无关测试或重启服务。
