# 2026-10-18 Codex FlashX low 建模复盘与 token 核算

本轮最小安装链四题独立非盲回归通过，任务已关闭；Delivery仍需Host恢复与审核补位。
10个保留原生线程、126个唯一响应的已知输入为8,373,261、输出41,311，合计
8,414,572 token。Delivery占输入72.69%，一次零缓存压缩占其未缓存输入74.25%。
应优先处理同一provider wait重复上报；本次只复盘，不实施建议或启动新运行。

## 范围、质量与时间

- session：`minimal-chain-20261018-codex-flashx-low`；唯一run：
  `minimal-chain-20261018-codex-flashx-low-r1`。采用代码`660ef8e`，全部角色配置为
  Codex / `glm-5.3-flashx` / `low`，Task/Profile为R4.3-026最小安装链。
- 原业务输入、全景／切片CQ审核、冻结四题及原评分范围不变。本次只查保留元数据、
  工具合同和原报告，不复制作答、隐藏题或评分点，不重新验收。
- 初建1轮、fresh semantic-start 1次，没有实质修模；原授权3轮，未用2轮已撤回。
  CQ原线程恢复是技术接续，不增加建模轮次。
- 2026-10-18 UTC+8：授权23:14:34.743，semantic-start 23:14:46.731，freeze
  23:18:26.567，正式handoff 23:21:21.597，接纳验收23:23:12.869，关闭23:25:15.419。
  授权至开始约12秒，开始至接纳验收8分26秒，授权至关闭10分41秒。
  这是墙钟，语义／技术／等待有效工时未知，不计算有效语义比例或故障扣除值。
- 两批原子应用，原关闭记录为revision 2、Build Session completed。原公开1/1、
  隐藏3/3报告均full_pass、完整分母、治理证据重验无漂移，冻结／model binding一致。
  本次核对两份原报告SHA256与关闭清单一致；资格均为non-blind-regression。
  这是复核原独立裁决，不是复盘者另行裁决，不外推完整工业服务或L2。
- 原关闭清单记载43个本轮进程退出、5个临时凭据撤回，资源／证据保留；本次未重启服务。
  第一阻塞为CQ `rateLimitExceeded`，Host经原线程`recover_provider`恢复并补位全景审核；
  后续切片走正式Host私有journal。因此自主完整交付不通过，模型质量通过单独保留。

原任务记录：gitignored `workspaces/minimal-chain-20261018-codex-flashx-low/`中的
`authorization.json`、`completion.md`及`final-*-verification.json`。原运行证据位于
`workspaces/modeling-runs/minimal-chain-20261018-codex-flashx-low-r1/`；Delivery证据位于
`workspaces/delivery-sessions/minimal-chain-20261018-codex-flashx-low/`。

## 关联需求验证与旧优化

| 需求／旧优化 | 本轮证据及结论 | 剩余边界 |
| --- | --- | --- |
| R4.3-019 | 部分验证；逐响应去重与10线程末次累计一致，补齐Consumer末段及Judge | Host／辅助／无数值失败请求、完整请求计时及账单unknown；不关闭全任务对账 |
| R4.3-022／030 | 部分验证；新任务／预算／起点实际进入v2，3次yield、2次原件补读均成功 | 重复wait仍推动事件变化；F1／F2有待调整，A5同条件净降耗未验证；F3／F4未启用 |
| R4.3-029 | 部分验证；Host私审交接成立，Delivery后续推进冻结、验收及关闭 | 本次自主完整交付未通过；恢复由Host补位，净成本转移不完整 |
| R4.3-024／025／026／023 | 部分验证；直接两批apply、实际治理读回、四题独立非盲回归 | 仅最小新建场景；其他操作、复杂表示／原工业范围未覆盖 |
| R4.3-020 | 追加实际窗口配置证据；Delivery 516800、生产及验收258400 | 本轮实际发生Codex压缩，不证明DSH压缩修复的压力效果 |
| R4.3-031—035 | 本次显式Codex，DSH专属效果不重判 | 保留C组正常路径和工程结论；本轮不验证DSH恢复、自动交接或默认切换 |
| R4.3-013／014／015／028及历史复杂消费反例 | 引用补读有局部正证据；恢复模型／早期反馈／已有模型增量未触发 | 不因未触发关闭或判失败；021继续暂缓 |

当前工程进展沿原交付记录；本次真实采用不反向抹去前组失败，也不将局部效果扩大成整项关闭。
需求结论同步至[v4.3](../../requirements/requirements-v4.3.md)，优化效果追加
[台账](optimization-tracker.md)，没有新增用户未确认的优化编号。

## Token 明细与核算方法

| 角色 | 唯一响应 | 输入 | 缓存输入 | 未缓存输入 | 输出 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Delivery | 28 | 6,086,173 | 5,235,008 | 851,165 | 9,834 |
| Modeling | 33 | 997,416 | 945,664 | 51,752 | 11,917 |
| Coordinator | 25 | 579,734 | 539,072 | 40,662 | 10,361 |
| CQ作者 | 12 | 160,292 | 137,856 | 22,436 | 2,626 |
| 独立Consumer（4线程） | 20 | 299,109 | 222,528 | 76,581 | 3,238 |
| 独立Judge（2线程） | 8 | 250,537 | 153,088 | 97,449 | 3,335 |
| **已知小计** | **126** | **8,373,261** | **7,233,216** | **1,140,045** | **41,311** |

输入已含缓存，不再相加；输出已含推理7,928，不重复加推理。已知总token为输入加输出
8,414,572。全体已知缓存率86.38%，Delivery为86.01%。不是费用或完整全任务成本。

原关闭时的`usage-report`只有累计快照且缺基线／快照归属，故安全返回unknown。
本次按原scope的线程绑定，逐个列入最终rollout，以真实`response_id`去重，补四Consumer
报告与`fresh_thread_id`绑定，并正确归类两Judge。独立既有工具生成新报告，未覆盖旧报告。
10线程响应和均与各自末次累计的input／cached／output／reasoning／total一致。
累计仅作交叉检查，不与逐响应结果相加。

四Consumer原报告快照早于末次响应，少记输入69,600、输出193；采用最终原生记录，
快照只作比较，不再计一次。离线工具仍披露累计基线未声明、空usage通知等局限；这些
不作为额外请求或成本相加。原件未闭合的失败请求保持unknown，不能由空通知推定数量。

Delivery真实压缩响应`resp_2026101823173259520347e43f44b8`：输入632,016、缓存0、
输出1,215，已计在Delivery合计；占其未缓存输入74.25%，占全体已知未缓存55.44%。
`compacted`事件23:17:51有真实response绑定，不能再额外加压缩成本。

核算原件、冻结字节／摘要、线程明细及新报告位于gitignored：
`workspaces/codex-flashx-retrospective-20261018/{scope.json,native-reconciliation.json,usage-report/}`。
可复用既有离线工具对同scope另选不存在的输出目录复算：

```sh
PYTHONPATH=. backend/.venv/bin/python -m modeling_team.usage_report \
  --scope workspaces/codex-flashx-retrospective-20261018/scope.json \
  --output-dir /tmp/codex-flashx-low-usage-recheck
```

Host本轮协调／私审／恢复与外部辅助调用未完整绑定，供应商账单／价表未提供，完整计时未知。
报告为usage／attribution partial、timing unknown、billing NOT_PROVIDED。

## 待调整项及逐项定位

1. **同一provider wait重复上报，已定位。** `provider-wait.jsonl`共824条，同一CQ
   wait的`issue-report-unavailable`占820条，仅一次observed、一次Host恢复及一次cleared。
   冻结Profile只允许Coordinator与Modeling互通，没有CQ→Coordinator边；
   `transport_mcp.TeamTransportBroker.report_issue`要求该边，Runner的
   `_report_provider_wait_issue`捕获RoutingError后只写不可用，下一次drain又尝试。
   `_check_provider_waits`每次仍走原循环。源头限流属于runtime/infrastructure；
   重复升级属于collaboration/routing，修改责任为Runner／Delivery投影，非业务模型。
   建议保留首个错误／当前Host恢复待办及真实状态变化，同一wait的无变化失败不重复
   上报／投递；不要为消除日志擅加CQ通信权限。T0下权限隔离仍必要，可收窄重复行为。
2. **输入累积及压缩，已定位机制、节省量未证明。** session有109个决策输入记录，
   73个只改变events；176次dispatch attempted、174 accepted、2 rejected。
   原生历史有173份host_observation文本项，约2.57MB；与dispatch不是同一口径，
   可能包含压缩历史保留，不把条目数当唯一原始投递／模型请求。实际数值响应只有28个。
   `_decision_events`将不同source offset推进chain，重复上报虽含相同业务状态仍属新事件。
   wait日志原件、事件进入输入、上下文压缩均可确认；压缩632,016输入不能全归因wait，
   尚无只移除wait重复事件的真实对照，不承诺可节省同等token或分钟数。
3. **“只有start_run工具”旧归因未证实。** 原授权／关闭说明以此解释Host补位，但
   原生session_meta实际注册41个动态工具，含recover_provider、request_host_action、
   read_delivery_artifact等；随后实际成功使用多个。现有证据不能证明启动时只挂载一个，
   也不能只凭注册断言每次供应商请求均可见全部工具。外发请求schema未保留，具体首段
   选择／可见性原因未定位；最小补证是既有供应商请求的工具名元数据，不需重跑模型。
   不据旧描述新增工具或改权限；Host恢复事实、自主交付未通过仍保留。
4. **Host请求与Runner请求账本混用，已定位。** Delivery用get_request_result查询
   私有Host action的slice-review request，收到request_id_unknown。该接口只查Runner
   submission ledger，Host action结果应沿原journal／host_actions；不是审核丢失。
   后续沿正确通道继续。建议只澄清现有ID／结果入口，不建设第二套相关账本。
5. **handoff过早一次，正确可恢复，已定位。** 23:20:56首次提交返回submitted后，
   业务回执为`cq_production_pending`（production deliveries未结算）；23:21:21
   原依赖就绪后新request获accepted，仅一条正式handoff证据。保留该application门及
   submitted／业务成功区别；建议按已有待办确认终态后提交，不删除保护或扩大编排。
6. **其他错误不误归质量。** provider-error原件39条responseStreamDisconnected /
   will_retry=true、1条rateLimitExceeded / false；通知数不是独立失败请求数。
   Delivery两次有界原件补读均成功，其中一次核对角色内只读命令失败并由Modeling自修复，
   未形成未知写入或最终语义失败。供应商内部原因及完整失败请求用量缺原件，不推测。

## 比较、建议顺序与完成边界

相对[DSH C组](2026-10-18-dsh-low-c-retrospective.md)，本轮Delivery输入观察下降73.96%
（23,374,584→6,086,173），但未缓存上升89.45%（449,272→851,165）。runtime、模型、
计数单元、故障、Host介入和实际压缩均不同；这不是030 A5净降耗对照，也不证明费用下降。
读取从C组28次／17次失败变为本次2次／0失败，支持本次合同采用改善，不作单因素归因。

优先建议沿029／030修同一wait的重复升级及输入，再澄清Host request相关入口；F3短线程
仍按原分批设计决定，不恢复021、不为本次小链重建监控。必要正确错误、授权、unknown、
真实治理读回及独立四题不能删减。后续获准同条件任务对比Delivery输入／未缓存／压缩、
完整任务转移、Host补位及原完整质量；节省量未实测，不能先关闭原预期。

本次没有代码／提示修改、semantic-start、修模或新验收，不恢复已撤回额度。
文档只做链接／格式／数值一致性与diff检查；这些检查不代替新独立验收或真实降耗验证。
