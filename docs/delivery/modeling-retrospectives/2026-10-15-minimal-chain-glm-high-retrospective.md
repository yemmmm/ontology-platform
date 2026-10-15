# 2026-10-15 最小安装链建模复盘

结论：**总体 PARTIAL，L1 Modeling quality 为 REVISE**。直接提交、一次原子应用、
治理读回、关联检查和独立消费／裁决已经实际发生；两概念一关系仍未取得完整语义通过。
四题实际执行、三题通过、一题失败，不将其称为知识覆盖率或严格盲测成绩。
最值得处理的是概念与实例的表示错误，以及生产收尾的错误反馈／旧清单门。

本报告为宿主复盘，不是新的独立验收；不修改历史题池、模型、裁决或授权账本。
用户仅要求复盘，建议尚未获准实施，不新增建模轮次。时间统一显示为 UTC+08。

## 范围与证据

任务为 R4.3-026 最小安装位置链，唯一业务源版本
`minimal-installation-chain-source-v1`，源字节 SHA-256
`ac3d7f91620f292b2a3dcd64d218b4f8d482353b96f5be4c3955e1318a090566`，
与 run 的 source-manifest／baseline 及输入清单一致；不将 Judge 读取内容摘要当源文件字节摘要。
采用配对 Task／Profile `r4-3-026-minimal-installation-chain` 和
`glm-flash-high`（`glm-5.3-flash`，requested/effective effort 均为 high）。
模型配置中的八角色键不代表实际启动八个生产角色；生产实际为 Coordinator、Modeling、CQ，
另有 Delivery 及后续独立 Consumer／Judge。

| 编号 | 本次核对原件 |
| --- | --- |
| E1 | [授权及三轮账本](../../../workspaces/minimal-chain-20261015-glmhigh/authorization.json)、[最终结果](../../../workspaces/minimal-chain-20261015-glmhigh/final-result.json)、[最终资源快照](../../../workspaces/minimal-chain-20261015-glmhigh/final-resource-check.json) |
| E2 | [实现及各次修复记录](../records/2026-10-15-r4-3-026-implementation-record.md)、三次 run 的 `evidence/semantic-start.jsonl`、`staged-decisions.jsonl`、`issue-report.jsonl`、`issue-control.jsonl` |
| E3 | [第三轮 baseline](../../../workspaces/modeling-runs/r4326-20261015-glmhigh-round3/baseline-manifest.json)、[候选 r2](../../../workspaces/modeling-runs/r4326-20261015-glmhigh-round3/stage3-neutral-graph/candidates/minimal-installation-chain-r2.json)、该 run 的 submission intent／receipt、治理响应及 [交接 v2](../../../workspaces/modeling-runs/r4326-20261015-glmhigh-round3/handoff-output/modeling/handoff/modeling-minimal-installation-chain-handoff-v2.md) |
| E4 | 第三轮 `acceptance-v3/reports/cq-batch-0003/attempt-0001/` 与 `acceptance-v3/public-regression/cq-batch-0003/attempt-0001/` 下的 batch-report／attribution；仅在宿主侧核对，不作为生产输入 |
| E5 | 第三轮 `evidence/app-server-events.jsonl`、`team-transport-events.jsonl`、`outer-input-receipts.jsonl`、CQ review／freeze、`cq-handoff-complete.jsonl` |
| E6 | [Delivery 会话事件](../../../workspaces/delivery-sessions/minimal-chain-20261015-glmhigh/session-events.jsonl)、`native/usage-events.jsonl`、`native/sessions/` 的线程生命周期回执；[本次私有用量 scope](../../../workspaces/modeling-retrospective-minimal-chain-20261015/usage-scope.json)、[既有用量工具输出](../../../workspaces/modeling-retrospective-minimal-chain-20261015/usage-report/report.md)、[样本及定位](../../../workspaces/modeling-retrospective-minimal-chain-20261015/evidence-summary.json) |

前置失败 `start1`、`start1b` 未产生 semantic-start，消耗零轮。
三次真实开始为 `r4326-20261015-glmhigh-start1c`、`r4326-20261015-glmhigh-round2`、
`r4326-20261015-glmhigh-round3`，各计一轮；无验收后实质修模，三轮／三次 fresh start，余零。
第一轮 semantic-start 代码为 `038b003`，第二轮 `02b6c1d`，第三轮 `6b7289a`。
第三轮 runner、Codex runtime、transport、精简 Modeling 指令／skill 及两份表示合同的
当前 SHA 与 baseline 一致，可以据此检查当时责任面，不能把缺陷解释为“旧提示未加载”。

## 关联需求的验证闭环

以下结论沿原验收条件分层；历史工程／独立功能证据继续保留。
本次最小场景没有 SQL Schema、跨 Ontology 或复杂条件，不关闭原小链对应的验收缺口。

| 需求 | 本次实际采用及结果 | 验证结论／缺口 |
| --- | --- | --- |
| R4.3-026 | 精简材料进入真实三角色；第三轮实际应用并独立完成四题，模型额外断言实例事实 | **验证未通过**：A2 源忠实度／独立语义结果不符合；A1／A4／A5 已有材料及配置证据保留；A3 时间线和部分用量可读，完整用量未知 |
| R4.3-024 | Modeling 经能力直接提交；修正引用后同目标继续；真实读回、关联扫描、资源关闭；无 Protocol 翻译或模型 dry-run | **验证未通过（本次最小场景质量）**：A3／A4 局部真实采用，A8 自查未发现概念／实例冲突，A9 独立质量不通过；既有工程 PASS 不撤销，跨 O／完整范围仍待证 |
| R4.3-025 | 四个显式变更编为单批，revision 0→1；真实 Batch／Attempt／索引 current；引用错误有原提交定位 | **部分验证**：确定性执行真实采用成立；只覆盖创建及单 O，更新／删除／跨批等沿已有工程证据，A10 联合语义不通过不能解释成编译器业务推理错误 |
| R4.3-023 | 原 Task 身份与禁止臆造实例的范围进入实际派单；Coordinator 未删除该要求，但接受了违反该边界的候选 | **部分验证**：派单保真局部成立；专用精简包及不同业务范围不能代替原 A2／A3／A6 的 Schema 约束／原小链效果验收 |
| R4.3-013／014／015 | 文件交接可用；错误接收通道被拒；迟到的旧 r1 重试指令经实际回执对账，未重复成功写入 | **部分验证**：正常成功回执的信任局部成立；目录交接、历史生产恢复及更大场景阶段反馈效果仍待证；最终公开回归不是早期反馈 |
| R4.3-019 | Delivery 数值事件和三轮 app-server 累计值实际留存；离线工具可读取 | **部分验证**：补正“完全没有 token 数值”；完整任务／逐响应／辅助评分／账单仍未知，Delivery 两线程有计数下降，不能按末值直接结算 |
| R4.3-016 | 本次沿台账核对需求、修正旧归因、保留失败与作用范围 | **部分验证**：新增一次实际运用证据，不以复盘作者自评关闭独立跨轮效果要求 |
| R4.3-001／R4.0-021 | 起点、暂停、应用、裁决与收尾可定位；有效活动未完整分类 | 最小链没有原 27 题／120 分钟性能目标；不新增固定预算，不计算语义有效工时占比 |

## 旧优化验证与待调整项

- **024／025：工程可用提升为真实局部采用，不能关闭完整效果。** 一次 application 及
  当前修订读回成立；024 的自查质量目标出现明确反例，台账标待调整。025 保持已实现待实测，
  注明单批创建实测成立；其余操作与最终质量／时间预期尚未闭合。
- **023、RETRO-07／08：保留已实现待实测。** 本次派单没有重写原范围；问题位于
  精简表示、候选选择及审核。旧非空／唯一／外键／时间反例未在最小链触发，不能用本次
  不同专用包宣布原修复成功或失败。候选 top-level unknowns 仅留交接的缺口继续披露。
- **RETRO-09：保持待调整。** 本次方向与非所有权含义得到正确消费，但原小链已返回
  时间／空值限定未充分回答的反例未重验，不以不同题集局部通过关闭。
- **013：文件可读局部成立，正确权限拒绝保留。** 两次 terminal 引用了只发布给
  Coordinator／其他接收方的材料，Runner 通道校验正确拒绝。改为正文后继续；不建议删除
  该权限检查，也不据此认定目录能力失效。
- **014／015：不重放成功写入成立，完整恢复／阶段效果待证。** r1→r2 仅为写前引用
  纠错，不计新修模轮。迟到重试请求未造成第二个 Batch；本次没有历史生产恢复实验，
  独立公开回答发生在交接之后，不冒称早期反馈收益。
- **RETRO-01／02／04／05／06、RETRO-20261014-01：保持待实测。** 正式 CQ 重新发布
  后冻结成功、14 个响应重放无漂移，但不等于缓存元数据反例、旧冻结身份及后续跨批
  绑定等路径全部重验；provider wait 出现也不等于 HTTP 400／402 状态纠正已触发。
- **019／020／022：保持待实测，021 保持暂缓。** 019 获得数值留存及离线采用证据。
  生产／验收线程观测窗口为 258400；不从配置推出成本改善。Delivery 有 469 条决策输入
  事件、3124 条分块投递事件及 4 个有数值记录的线程，且发生 Root 接管；这些不是模型请求数，
  不能证明唤醒均冗余、022 净节省或 A13 自主交付，也不支持重开 021 的客户端改造。

没有新增用户确认的优化项，没有关闭旧项。以下新建议不自动登记为需求或授权实施。

## 时间、质量及用量

| 时点／区间（UTC+08） | 已证实含义 |
| --- | --- |
| 12:28:16.689 → 12:45:50.978 | 授权到首个 semantic-start **17 分 34 秒**，满足 20 分钟开始规则；其间有两次零轮次预启动失败 |
| 第一轮 12:45:50.978 | CQ phase／issue 提示纠正后，legacy stage3 阻断 scope 绑定；没有模型写入 |
| 第二轮 13:19:00.297 | Coordinator provider 限流，issue 投递误作不可恢复失败；没有模型写入 |
| 13:30:22.865 → 15:35:42.547 | 用户暂停到授权账本中的“继续”，**2 小时 5 分 19.682 秒**；期间包含技术诊断／窄修，不能记成语义建模时间 |
| 第三轮 15:42:31.789 → 15:56:48.500 | **14 分 16.711 秒**到首次真实应用；只有这次产生模型，revision 1 |
| 15:54:44.164 → 16:03:43.147 | 冻结等待 issue 的恢复等待／最终派发跨度 **8 分 58.983 秒**，与上述应用过程重叠；不是可全部扣除的故障时间 |
| 15:56:48.500 → 16:24:21.691 | 应用后到生产只读交接 **27 分 33.192 秒**；含技术收尾、审核、消息等待，不能全部归为平台 CPU／可节省时间 |
| 16:31:32.776／16:37:10.924 | 两组独立报告分别落盘，共四题三通过；同 freeze、同模型状态，未拼接不同模型的通过题 |
| 16:40:43.692 | 最终资源快照／收尾截止；没有完整 PASS |

授权到截止总墙钟 **4 小时 12 分 27.003 秒**；仅扣明确用户暂停区间，剩余观察跨度
**2 小时 7 分 7.321 秒**。它包含技术修复、等待、生产和独立验收，不是有效语义工时，
也不是扣故障后的无故障性能。旧记录暂停终点采用派发时点 15:35:41.170，与账本确认
相差 1.377 秒；本报告统一采用账本“继续”时点，不覆盖旧记录。

首个有效回答的精确事件时点、语义／技术／等待的有效工时及其占比仍 unknown；
不据此新增逐工具监控或性能门。三个 scope／模型不同的前后任务不直接计算提速。

**用量补证**：E6 的现有 `modeling_team.usage_report` 离线输出为 usage unknown、
attribution partial、timing unknown、billing NOT_PROVIDED。生产／验收 app-server 中的
13 个线程存在可复核、单调的累计区间。仅取每线程首个已保留非零累计值到末值的差：

| 样本 | 线程数 | 输入增量（包含缓存） | 缓存输入增量 | 输出增量（包含推理） |
| --- | ---: | ---: | ---: | ---: |
| 第一轮生产 | 3 | 1508569 | 1446464 | 30671 |
| 第二轮生产 | 3 | 604459 | 549120 | 12798 |
| 第三轮生产及独立验收 | 7 | 4508518 | 4228864 | 79630 |

这是文件内已观测样本增量，不是整轮 token 总数、费用、API 请求吞吐或提速证明。
首个非零值之前的输入、Delivery、Root、无 usage 失败及辅助评分未计入该表。
Delivery 有 134 条累计事件、四线程，其中两线程有数值下降／归零，不能任取最大值、
相加重叠或按末值算账。生产 provider-attempt 没有 thread_usage 不等于 app-server 没有数值。

## 已识别问题的定位

所有本次已识别问题均列于下表；“修复／采用”只覆盖说明的窄分支，不扩大到全流程。

| 问题／原始位置 | 第一层、原因及把握 | 修复／采用／剩余边界 |
| --- | --- | --- |
| 预启动 roster role 缺失；E1 prelaunch、E2 | platform-contract，已定位：model profile 按语义 role 键控，精简 package ID 未回落其声明 role | `89291a3`；其后三次角色启动实际成功。不是模型质量失败，消耗零轮 |
| start1b `app-server closed its output`；E2 | platform-contract，已定位：Modeling capability 已配置挂载，socket 未 start；不是退出后 secret audit 主动 kill | `984abd4`／`038b003`；后续 endpoint-started、实际调用成立，消耗零轮 |
| 第一轮 CQ draft phase 不进正式冻结池；E2 review／outer receipt | collaboration/routing，prompt-contract 已定位：`panorama-draft`／`slice-draft` 不属于正式 review phase | `1afabb6`；原线程更正，第一轮 freeze 成功；第三轮正式 phase 实际采用 |
| 已自动 resume 后再次手动 resume；E2 issue-resolution/control | collaboration/routing，已定位：resolution 路径已持久化并自动 settle/wake，第二次控制是 stale；不是 resolution 丢失 | `1afabb6` 的后续提示纠正已在第二轮前提交；第三轮未出现同一 duplicate-resume 反例 |
| 第一轮 `stage3_missing_artifact`／`scope_binding_required`；E2 | platform-contract，已定位：旧 slot 前置在合法 scenario-map／topology 前阻断当前 direct task | `41769b3`／`02b6c1d` 收窄旧门适用任务，第三轮 scope 绑定及 apply 成功；旧 unified 校验保留 |
| 第二轮限流后 `issue Coordinator delivery failed`；E1/E2 | 上游触发 runtime/infrastructure；终止原因 platform-contract，已定位：只有 runtime_recovery 类 issue 获 provider-wait deferral，普通 business issue 被 fail_issue_rebind | `6b7289a` 聚焦回归通过；第三轮加载该修复，但没有同类 Coordinator provider-wait，**原故障分支真实恢复仍待证**；第二轮遗留资源清理有快照 |
| 第三轮 CQ 问题对象多字段、pause 多 `reason`；E5 app-server 1732／8062 | collaboration/routing，已定位：闭合字段合同使用错误；普通可恢复输入错误 | 依据明确反馈去除字段后同 run 继续，不新增硬门或轮次 |
| 冻结前提交、5044 次 resume waiting；E5 capability／issue-control | collaboration/routing，已定位：Modeling 在 freeze 前提交并将必要等待升级 issue；Runner 等 reporter 活跃 turn 结束才真正发 resume，每 tick 重新记录等待。07:54:44 有决议，08:03:43 才结算；此前模型已应用，不能将整段算无进展 | 旧 r1 派单后按真实应用回执对账，无重复写入。等待本身保护活跃线程可保留；普通 freeze 等待不应借助 typed issue 形成跨 turn 依赖。不能把 5044 行当 5044 次 Agent 唤醒 |
| 候选引用不可达、谓词裸 item ID；E5 app-server 15437／17945 | collaboration/routing，已定位：发布／工作目录不等于指定 run-relative candidate 已可读；`value.predicate` 需 definition_ref，不能写裸 item ID | 修正可读发布／引用形式，r2 仅技术引用变化，四个原 change 同批应用。准确 not_written 反馈有效，应保留 |
| 无效检索过滤及 5 秒 timeout；E5 app-server 19192／19226／19355 | 无效过滤属 collaboration/routing，已定位：把 candidate kind 当检索 resource_types；超时定位到 runtime/infrastructure 的本地 bridge 边界，`read_proxy_mcp._proxy_call` 固定 5 秒，实测 5005／5006ms；尚无证据指向具体服务端阶段 | 去除过滤、较小 lexical 查询及实际 IRI 读取成功；不把失败当内容不存在。服务端原请求耗时／是否仍执行未留明确绑定，不能确认增大 timeout 的净收益 |
| 两次 terminal `material_forbidden`；E5 app-server 22321／41328 | collaboration/routing，已定位：材料 recipient 与 terminal 的 runner 接收通道不一致；`handoff_materials.authorize_ref` 正确拒绝 | 改成合法正文后继续；保留通道授权，建议明确原接收方引用不可跨通道复用 |
| Modeling 四次 terminal 被报“query_required”；E5 transport 2—5、app-server 22701／23405／23564／24549 | **platform-contract，已定位并纠正旧归因**：对应时间为 08:00:31—08:03:06 UTC，issue-1 尚 pending，到 08:03:43 才 resume；`Runner._terminal_report_guard` 首分支直接拒绝 pending issue。该角色 fallback_eligible 为 false，不存在证据证明其旧 Protocol 检索状态真的未满足 | Broker 把 guard 的所有拒绝包装成固定 Protocol 检索错误，误导重复 query／inline verifier。原“modeling_read_proxy 回调不满足 terminal gate”没有源码支持；事后未再尝试 completed，不能宣称同一检索缺陷仍存在 |
| Coordinator terminal／handoff 被拒；E5 staged 最后一行、outer 20—22 | **platform-contract，已定位**：Coordinator completed 走 `staged_checklist_issue`，回执明确 `acceptance_checklist_missing`；而 cq_semantic handoff 已明确旧 008B checklist 不是前置。第一次 handoff 时 Coordinator 尚无终态，报 scope unauthorized，待如实 blocked 后原 handoff 成功 | 不应补造旧 checklist 或重复语义查询；按 T0 收窄不适用旧门、返回真实阻塞原因。独立 ready／write reconciliation 已保护写入完整性，不需要这个旧清单重复保护 |
| 切片身份漂移及三次冻结；E3 map／E5 CQ | collaboration/routing，已定位：`minimal_installation_chain` 与候选 `minimal-installation-chain` 不一致；Coordinator 在读实际 r2 后纠正地图，CQ 旧 scope 需新正式 review／freeze，不能改冻结原件 | 最终第三个 freeze 与 map／候选一致，scope 更正的在途 review 再发布多一个 successor；同源最终题池及模型绑定已核对，没有靠删题求通过 |
| 概念变成具名个体及实例事实；E3/E4 | **modeling-quality，已定位，高把握**：原 Task／源／派单都不提供实例；候选选择 entity/create_entity 并显式 relation，治理响应确为 NamedIndividual＋安装断言；Consumer 使用该事实，Judge 据源裁决失败 | 文本定义、方向和非所有权局部正确；候选 13 项 unknowns 留顶层，各资源 unknowns 空，且 Coordinator 审核未识别语义层级冲突。精简说明“entity/property/relation suffice”“need not introduce Classes”可能诱导该选型，**此因果为推断**；不能甩给检索缺失或编译器擅自选择含义 |
| Delivery 多次上下文重启及 Root 接管；E6 | runtime/infrastructure，原生失败已定位：线程 `01a13dde-3aad-74e1-819b-e0cec5babc70` 在05:22:23.531Z、`01a13e88-815b-7f23-ac79-bcb6e3e1c7db` 在08:05:20.108Z 的task_complete均为 `context_window_exceeded`，此前分别有05:20:14／07:57:19 compaction；它们对应exit0，不能把进程正常退出当任务成功。另四次exit-2是SIGINT关闭，不自动算模型崩溃。输入中具体哪部分导致耗尽仍部分定位 | 已核对六个线程的原生生命周期、关闭记录及Host接管事件；无原生证据把耗尽单独归因某字段或469决策包／3124分块。A13 unverified；可做的最小下一定位是按既有上下文／compaction回执与决策包字节引用核对累计来源，净收益仍需可比观察，不建设新监控平台 |

### 对旧收尾归因的纠正

上述源码与第三轮 baseline 摘要一致：`runner` 为
`3b5aed3f10e170455733740beb59391d2ab077df48d9b16c435fd91d22476236`，
Codex runtime 为 `712c752a9f83ee7071afd665839bef4878567e614c34dad8584753b5daf36cba`，
transport 为 `d1184d3f308ed5fd01a4eba8de9d43982fe86abb6477a5d465473108ce5a1f95`。
`fallback_eligible` 仅给 create/v2 Protocol；精简 Modeling 不在其中。`report` 对任何 guard
拒绝统一返回 `TERMINAL_REPORT_GUARD_ERROR`，因此错误文字不能用来证明检索状态根因。

原 live-partial、final-result 及角色 blocked 摘要保留当时归因。本报告追加纠正，
**不修改其原字节、不改历史状态**。生产闭环仍 PARTIAL，但修复对象应是 pending issue 的
真实反馈、普通等待的采用方式及 cq_semantic 的旧清单适用范围，而不是增加 Modeling 检索回调。

## 建议顺序及最小验证

1. **先修当前最小链的概念／实例表示与审核。** 当前精简说明把 entity＋relation 当作足够
   表示 → 先让 Modeling 依据源明确“概念定义”与“实例事实”的区别，再选择既有支持的
   Class／relation_type 或能明确表达概念层级的现有表示；同步短合同及现有 Coordinator 自查，
   不一律强制 Class，不加 SHACL、平台语义裁判或逐字段新台账。025 已有相关 create 能力，
   先用现有合同验证适用性，不预设必须扩平台。预期减少同类语义返工，分钟数待测。
   获准实质修模后保持唯一源和完整四题范围，实际应用／读回并由原独立流程重验；
   若现有表示仍产生实例含义，保留失败并再定位，不靠修改答案或降低 unknown 要求通过。
2. **纠正 terminal 的真实原因，并移除当前模式不适用的旧 checklist 门。** 当前所有 guard
   拒绝 → Protocol 检索错误，Agent 反复 query → 按现有分支返回 pending issue 或旧清单原因，
   仅在 full_joint 适用场景保留旧清单要求。活动 issue 与不确定写入保护保留；独立 handoff
   的 apply closure／授权／scope／只读封口继续工作。先做有界“活动 issue、无 issue、
   cq_semantic、full_joint”回归；下次获准运行确认不再误导 query，且独立验收仍能正常进入。
   不按 27 分钟收尾跨度承诺等额节省。
3. **沿既有 Task 执行 freeze 后派单，普通等待用既有反馈。** 当前 freeze 未就绪先 submit，
   再升级 issue → 候选可先准备，提交等待现有 Host freeze 确认；CQ／地图复用同一实际
   slice_id，跨阶段更正走已有新 review。Runner 对真正 busy reporter 的可恢复等待保留，
   不新增尝试上限／自动 kill。验证实际提交时序、issue 结算与迟到指令对账；失败原件仍保留。
4. **保持部分用量证据，先解决已有口径缺口。** 当前把 provider-attempt 无数值概括为全程
   unknown → 使用已存在的 app-server 与 Delivery 数值源，显式区分单调样本和 reset 缺口。
   不为补账启动新建模、打供应商请求或新建遥测平台；费用／完整总量待现有原生回执和账单
   有授权时对账。缓存命中不能补偿语义失败，也不从本次不同范围材料减量推出提速。

建议 1 和 2 分别解决已证实质量缺口与错误返工；3 是现有提示的采用纠正；4 先复用数据。
这里只提出可审阅方案，尚未实施上述新改动。第二轮 provider-wait deferral 的真实同类恢复、
复杂原小链／完整场景、原 27 题与性能、重复性及 Delivery 自主交付继续待证。

资源状态仅引用 16:40:43 的最后快照：revision 1、一个 Batch、Build Session completed、
active lease 及项目模型 key 均为零；Team／Consumer 只读保留。复盘未重新查询活服务、
未启动模型、未修改写入或凭据。再做实质修模须新增轮次授权；本次不发起运行。

## 本次记录检查

新增／改动本地链接、Markdown围栏及diff空白检查通过；两份原报告字节摘要、同源freeze／
模型绑定、执行分母、裁决数及原报告中的14响应重放记录已核对，源字节及相关运行代码／
提示与baseline摘要一致。上述为证据／文档检查，没有重跑语义验收；仅改文档，不运行
后端／前端套件或重启服务。
