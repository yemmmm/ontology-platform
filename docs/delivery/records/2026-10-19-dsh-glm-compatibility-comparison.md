# 2026-10-19 DSH GLM 兼容与 Codex 同场景对比

用户要求在 DSH 中以 `glm-5.3-flash low` 执行一组任务，与最近 Codex 建模对比；
发现原隔离适配仅支持 DeepSeek 后，用户明确授权“补齐 GLM 兼容后运行”。
本次沿 R4.3-031／032／033／034 扩展精确 provider 接线，不改变建模业务含义或验收合同。

## 最小兼容范围

- 新增独立 `glm-messages` 目录路由，仅接受本次获准的 `glm-5.3-flash / low`；
  原 `glm-direct` Responses 路由及 Codex 默认保留。无自动回退、模型重命名或档位降级。
- 固定上游 `https://open.bigmodel.cn/api/anthropic/v1/messages`，复用宿主持钥、
  TLS、流式原字节转发、失败分类、凭据销毁及数值用量记录。官方兼容地址依据
  [智谱 Claude Code 文档](https://docs.bigmodel.cn/cn/coding-plan/tool/claude)。
- 复用固定 DSH Messages codec，单独注册 GLM provider；冻结本地 composition 摘要与
  实际有效绑定。原 DeepSeek 插件、工具集合／schema、资料隔离、控制与独立验收保持。
- Delivery、生产及独立 Consumer/Judge 全部显式 DSH／GLM。GLM credential 复用平台已有
  私有文件，只给隔离角色临时代理 token；没有复制 DSH 网页保存的另一份密钥。
  真实上游小请求 HTTP 200、响应模型精确，low 原样发送；不由响应推断供应商内部推理预算。
- 已核对用户 DSH 网页 provider `zai-coding-cn` 及默认 `glm-5.3-flash`，本地模型目录列出
  `glm-5.3`／`glm-5.3-flash`／`glm-5.3-highspeed`／`glm-4.6v`，前三者支持 low。
  网页既有 pi-ai 配置不注入隔离 Team，不修改 DSH 全局设置或密钥。

GitNexus 未收录新符号，impact 返回 UNKNOWN／target not found；本次采用直接调用点检查，
不声称图覆盖。受影响入口为 Delivery、生产 roster、验收 child 及生产凭据恢复。
未修改 backend/frontend，无产品服务重启。保留工作区此前无关未提交变更。

## 对比合同与原件

基线 `minimal-chain-20261019-token-opt-c-r1`；本组
`minimal-chain-20261019-dsh-glm-low-r1`，使用同一最小安装链源与 Task、同语义 Profile 的
DSH 版本、新项目新 scope。独立验收保持原公开1题／隐藏3题完整分母；本人工场景为
非盲回归，生产不接收私有答案或旧模型。Host 仅按既有职责逐点私审 CQ，不代写模型。

工程准备耗时与真实 semantic-start 至完整独立验收墙钟分开。对比全部绑定角色用量，
缓存是输入子集，推理是输出子集，缺失值及账单保持 unknown。不同协议、运行时及窗口
是实际差异，单次样本不做因果或完整费用结论。新增兼容成本单列，不隐藏到运行收益。

私有原件：`workspaces/minimal-chain-20261019-dsh-glm-low/`；保留授权、工程各轮日志、
上游探测摘要、Codex 基线数值、配置和真实运行证据。默认按一次任务的三轮上限管理，
fresh-start 与实质修模分开；成功后不为耗尽额度追加建模。当前任务未另发用户 stop，
正常完成按原合同保留只读 standby。

## 验证进度

新覆盖先红；GLM profile／原生 Delivery／生产隔离三项通过；当前 Consumer/Judge 两路
共20项通过。初轮曾发现验收 child 的 provider 检查依赖生产 run 属性，已收窄为传入
当前真实 binding；原失败日志保留。目录新增路由的原封闭集合断言已更新。
全量 Team 回归及真实运行结果随后追加；工程通过不代替真实 L0 或独立语义 L1。

当前最终专项验证：`test_dsh_glm`＋`test_messages_provider_proxy`共21通过；
`test_dsh_acceptance`两provider共20通过；`test_model_routing`77通过。
广泛Team套件按本次有界目标中止于612通过／2跳过／62项子测试，明确不是全量PASS；
另外生产／Delivery控制的相关回归保留完整日志，不与有交叉的轮次相加。
未运行backend/frontend套件，因为本次没有修改其代码。

## 真实结果与最终对比

**结论：本最小链独立非盲L1为4/4 PASS；DSH本轮更慢、记录输入更多，未证明降耗或费用下降。**
同一scenario和Task，除runtime／profile_id外Team Profile逐项相同；两轮冻结四题的题目、
必答点、未知、证据引用、可见性及内容版本规范化后完全相同。新旧代码差异仅本次兼容。

| 指标 | 最近Codex C组 | 本次DSH GLM low | 本次变化 |
| --- | ---: | ---: | ---: |
| 初建轮次／fresh starts | 1／1 | 1／1 | 无实质修模 |
| 独立非盲回归 | 公开1/1＋隐藏3/3 | 公开1/1＋隐藏3/3 | 同完整四题 |
| semantic-start至完整验收回交 | 10.86分钟 | 14.19分钟 | +30.60% |
| Delivery原生记录输入token | 6,919,702 | 21,418,062 | +209.52%（3.10倍） |
| 全链原生记录输入token | 9,930,615 | 24,586,921 | +147.59%（2.48倍） |
| 全链记录未缓存输入token | 430,007 | 787,881 | +83.23% |
| 全链记录输出token | 38,057 | 62,959 | +65.43% |

全链包含Delivery、Coordinator、Modeling、CQ、四个独立Consumer和两个独立Judge，
缓存／推理不重复相加。完整逐角色数值、原件摘要、截止点、模型身份及限制见
[数值证据](../evidence/2026-10-19-dsh-glm-low-comparison.json)。DSH原生190个数值响应，
与190个Provider响应计数对应，无重复事件冲突。输入按原生totalTokens-outputTokens
记录，未缓存／缓存读取也单列。**这不是完整供应商账单对账**：GLM把input/cache-read放在
流尾message_delta，原DeepSeek严格采集器将该位置标无效；固定DSH原生translator实际读取
流尾并保留数值。cache-write／reasoning字段缺失仍unknown，不填零、不伪称原代理完整。
本次没有为修补计量或提升对比结果再开模型任务；R4.3-019／034计量完整性仍PARTIAL。

当前外层Host为gpt-6.1-sol，与原C组glm-5.3-flash low Host不同。数值截止点已另外披露
兼容准备输入9,050,507、监督／对比输入16,352,288，总输入25,402,795、未缓存449,451；
当前响应、后续记录及最终答复尾部未计入。不能把Host或一次性开发成本隐藏到运行收益，
也不能把模型／Host／协议／窗口／故障路径不同的单样本差额归因于DSH本身。

### 实际阶段与阻塞处理

- 01:07:58.459970Z发生semantic-start，初建1轮；01:11:14.630050Z冻结完整四题。
- 两批application于01:11:21、01:11:35成功，revision0→1→2；治理读回、association
  和资源封口完成。没有apply重放、不确定写入或新的实质修模。
- CQ四次错误handoff资料读取最终自行纠正；没有Host手工搬运地图或代写业务模型。
- Modeling在真实新公开投影仍排队时三次终态拒绝，随后issue-1。Host重放连续seq0..190，
  核清九条输入全部settled、空inbox、无gap/conflict。T0复核保留保护实际未消费输入的守卫，
  没有删除校验或修平台代码。Coordinator误以为队友报告无需bound pause；Host技术补位
  使其经现有delivery_guidance完成pause，宿主guidance接受后原session恢复，随后终态接受。
  原Host consult在非只读阶段被正确拒绝，记录该操作入口错误，不掩盖为平台缺陷。
- issue_resolution于01:17:31.058973Z被接受，01:17:47.984549Z实际recovery-effective；
  01:18:24.417750Z正式production handoff接受，无pending／unknown写入。
- 公开及隐藏独立验收均为runtime=dsh、glm-messages／glm-5.3-flash／low；实际有效绑定
  及隔离工具有原件。两报告同freeze和model binding，未执行题、模型漂移、证据重验漂移为空。
- 01:22:09.673977Z接受complete_cq_acceptance（cq_verdict=pass）；
  01:22:44.416115Z接受standby。原模型、Team、Delivery及验收owner保留只读待命。
  此后未追加建模；1/3已用、2轮未用，不恢复旧关闭组的任何额度。

Host介入包含正常两次CQ私审及额外技术排队／issue握手补位，因此不称DSH完全自主交付PASS。
Delivery将这次无代码的技术guidance描述为“宿主平台修复”不准确，以Host原件为准。
原状态派生仍列历史issue_wait／cq_acceptance_closure；以实际accepted验收及standby回执
区分当前完成事实和历史首次阻塞，未改原事件去伪造干净终态。

为防止再次误读既有issue合同，收口时仅补充minimal-chain-coordinator权威提示：队友的issue
同样必须先bound pause，即使语义写入已经完成。配置validate通过；这是instruction-only纠正，
未重载本run冻结提示，未以本次结果声称新提示效果通过，也未启动新semantic start。
计量和重复唤醒后续优化没有在本任务扩展实现。

最终工程相关长回归为149通过、1项旧封闭目录断言失败；只修正新增路由对应断言后，
该模块77项全部通过（源码未再改），与前述21／20专项有交叉，不相加冒充一次全量。
最终相关链接、JSON、配置validate及git diff格式检查通过；没有backend/frontend变更或重启。

## 2026-10-19 Delivery 优化覆盖补查

用户追问额外token是否来自Delivery优化未覆盖DSH。本次仅分析上面两组保留原件，
未发起模型请求、修模、验收或生命周期动作，未修改运行代码。
结论是：**共用优化已进入DSH，但GLM计量异常与决策唤醒的交界存在漏覆盖；不是整套优化未接入。**
归属为030／022／032的按需决策与输入，以及019／034的provider计量。
完整数值与统计口径见[补查证据](../evidence/2026-10-19-dsh-delivery-optimization-analysis.json)。

### 已覆盖的优化与实际成本

Codex C的`ffd55e7`与DSH启动时`bb51c4e`之间，`delivery.py`、Delivery package指令及
Delivery skill无差异。DSH实际接收v2输入；不变task_context、快照和目标各省略107次，
历史省略108次，说明稳定输入裁剪确实采用。两边均未实施／启用030 F3阶段短线程和
F4机械连续动作，021仍暂停，不能将这些共同未实现项归为DSH专属回退。

| 指标 | Codex C | DSH GLM |
| --- | ---: | ---: |
| Delivery原生模型响应 | 49 | 78 |
| Delivery累计输入token | 6,919,702 | 21,418,062 |
| 每次响应平均输入token | 141,218 | 274,591 |
| 实际v2包平均紧凑UTF-8字节 | 10,622 | 9,072 |
| `yield_delivery`调用 | 16 | 47 |
| 全部工具调用 | 37 | 70 |
| 逻辑决策输入中仅events变化 | 20/57 | 71/109 |

Delivery增加14,498,360输入，占全链增加14,656,306的**98.92%**。响应次数增加59.18%，
平均请求输入增加94.44%；新增v2包平均反而小14.59%。这说明大头是更多往返与累计历史
反复进入后续请求，不能用单包裁剪成功推导整轮降耗。字节按实际包的紧凑JSON计算，
不等于协议线长或供应商token。DSH初始bootstrap分页使112个包对应109个input_id；
Codex的57个逻辑输入含一条未消费收尾，实际送达56个包，不混成模型响应数。

### 明确漏覆盖：GLM流尾计量被反复送入决策

1. GLM把`input_tokens`及`cache_read_input_tokens`放在流尾`message_delta`；现有
   `MessagesUsageObserver._event`仅允许在`message_start`更新这两项，将其标为
   `input_outside_start:*`。本次生产Team的**85个成功HTTP 200响应全部如此**。
2. 共用`_is_decision_event_noise`仅排除`usage_complete=true`且无usage_issues的成功
   DSH用量回执，因此这些数值采集缺口继续改变Delivery的events输入。
3. **42个逻辑决策输入的变化只有这类计量告警**，其中38个含1条、4个含2条回执。
   这是实际缺少业务决策变化的输入，不能把42直接当模型响应次数或承诺节省token；
   busy steer可合并输入，原始回执也并非可以丢弃。

DSH原生translator实际读取流尾数值，故已有原生输入统计仍可复算；采集完整性和账单
结论仍PARTIAL。cache-write／reasoning缺失保持unknown，即使纠正位置，也不能把
缺值填零以获得`usage_complete=true`。最窄建议是兼容实际GLM字段位置，并沿既有输入
通路保留首个计量缺口及状态变化、避免同类持续缺口每次都要求Delivery重新解释等待。
真实模型失败、断流、未知写入、用户控制及需要处理的错误继续及时送达。

原生DSH有8次turn开始和8次自然结束，但发生47次yield；第二个turn内即有24次yield。
这说明yield工具已接入，却不等于每次已经结束推理，连续的新输入仍可续推。
不能仅凭注册工具、自然结束计数或缓存率判断F1按需等待的净效果通过。
实际主动状态查询仅1次、原件补读仅2次，本次大头也不是反复主动读全量状态。

### 另有返工，不能全部归到计量告警

- DSH调用`start_evaluation`6次，前4次漏必填`mode`，实际仅启动公开／隐藏2个验收。
  保留的`host/inspect`工具schema确实将mode列入required，接线没有丢失该字段。
  原件记录4次`ValidationError`，但共用工具包装仅返回
  `delivery_tool_failed: check tool schema and bound inputs`，Agent转而试路径／runtime，
  加入`mode=cq-acceptance`后成功。缺字段由调用方触发，准确可恢复反馈缺失属于共用
  platform-contract缺口；Codex本次未触发，不是DSH独有实现。
- 前述issue排队／pause握手恢复也增加等待和宿主补位，保留其第一阻塞与原件。
  47次yield中31次是相对Codex增加值，占多出的33次工具调用的大部分；并非每次yield
  或这段故障期间的全部输入都可删除。不能把所有差额推算成修复告警后的可节省量。

当前030／022／032保持部分验证，追加“GLM计量缺口重复进入决策”待调整项；共用v2及
稳定输入省略的正证据保留。019／034计量和净成本保持PARTIAL，原820／522特定故障
未触发，不重判既有待实测子项。本次不新增未经确认的优化编号或实施授权。
建议先处理上述provider计量与重复告警，再给工具schema错误准确缺字段反馈；之后沿
030既定顺序评估阶段短线程。未来同条件运行须另沿授权执行，仍保留完整四题与独立验收，
同时核对Delivery和全任务数值，不以本次离线诊断宣称已修复或已降耗。
