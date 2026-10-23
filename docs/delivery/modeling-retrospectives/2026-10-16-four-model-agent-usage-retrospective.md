# 2026-10-16 最近四轮模型／Agent用量复盘

范围：FlashX low、Flash low、FlashX high、Flash high，均为R4.3-026最小安装链，每组实际1轮、1次fresh start；high两组并行。不是更早的前三组修模实验，也不把每组三次授权当作三次实际建模。

结论：四组保留的公开1题与隐藏3题报告均full_pass，无未执行题，标为non-blind-regression。这里只复核原裁决及运行绑定，不作新的独立验收；四题通过不代表完整工业场景、增量模型感知或自主交付通过。

## 口径与证据

- 时间主表为semantic start至平台验收完成（Flash low取最后一份报告落盘）；不含不可精确确认的用户消息至登记准备时间，也不是完整收尾时间。首写仅代表首次apply，不代表完整模型。
- token为本次原生线程最终留存累计值，已按真实thread去重；各原生线程无计数下降，且逐response_id去重用量之和与最终累计input/cached/output完全一致。Consumer有原生文件优先采用其最终累计；high Consumer使用batch报告中真实逐响应increments。
- low四个Consumer的task快照均早于最终原生计数，漏了末次响应；没有把两份相加。high Consumer的metrics_complete=false，完整覆盖仍标partial。宿主根Agent、辅助检索模型及供应商账单未纳入，不能称整轮完整费用。
- 缓存率=Σcached_input/Σinput，输入包含缓存；output包含reasoning，不能重复相加。不是请求命中比例，也没有套价格估算费用。
- token截点为各绑定线程最后保留usage（包括收尾／待命前后实际调用），时间截点为语义验收，两者边界不同；精确末次时间与来源见statistics.json。high仍保留待命，不从存活时间计算耗时。
- 分角色耗时为已完成turn区间并集，各线程再累加，包含工具和turn内等待；跨Agent并行不可相加当端到端。Consumer统一用task wall；Judge缺task_complete，另报会话保留窗口。它们均非纯推理时间或有效语义工时。

## 四轮总览

| 模型／effort | 首写 | 至验收 | 输入token | 输出token | 其中推理 | 未缓存输入 | 缓存率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| glm-5.3-flashx / low | 4:39 | 16:02 | 16,383,924 | 59,340 | 15,656 | 1,738,420 | 89.39% |
| glm-5.3-flash / low | 7:59 | 20:07 | 15,202,872 | 47,760 | 11,837 | 1,639,032 | 89.22% |
| glm-5.3-flashx / high | 8:59 | 21:30 | 16,381,965 | 111,034 | 65,350 | 1,769,997 | 89.20% |
| glm-5.3-flash / high | 15:51 | 29:48 | 9,638,658 | 95,743 | 56,927 | 1,742,786 | 81.92% |

时间格式为分:秒。FlashX low较high本样本验收早约5分28秒；Flash low较high早约9分41秒。high有并发、限流、不同协作／观察输入及收尾边界，不能归因effort的净影响。

## 分Agent统计

| 配置 | Agent | 耗时口径对应秒数 | 输入 | 缓存输入 | 输出 | 缓存率 |
|---|---|---:|---:|---:|---:|---:|
| flashx-low | modeling | 276.8（turn累计） | 1,962,795 | 1,879,168 | 17,778 | 95.74% |
| flashx-low | coordinator | 367.0（turn累计） | 1,452,800 | 1,405,120 | 16,916 | 96.72% |
| flashx-low | competency-question | 93.8（turn累计） | 300,488 | 275,840 | 2,869 | 91.80% |
| flashx-low | Consumer-hidden | 185.2（任务累计） | 269,637 | 228,032 | 2,570 | 84.57% |
| flashx-low | Judge | 26.5（留存窗口） | 140,122 | 13,824 | 2,095 | 9.87% |
| flashx-low | Consumer-public | 49.9（任务累计） | 135,898 | 106,752 | 1,812 | 78.55% |
| flashx-low | Delivery | 735.2（turn累计） | 12,122,184 | 10,736,768 | 15,300 | 88.57% |
| flash-low | modeling | 363.7（turn累计） | 1,399,739 | 1,334,400 | 11,710 | 95.33% |
| flash-low | coordinator | 648.7（turn累计） | 753,156 | 716,608 | 14,801 | 95.15% |
| flash-low | competency-question | 121.2（turn累计） | 217,011 | 193,024 | 2,771 | 88.95% |
| flash-low | Judge | 132.1（留存窗口） | 390,172 | 311,936 | 4,388 | 79.95% |
| flash-low | Consumer-public | 42.0（任务累计） | 76,448 | 57,664 | 1,123 | 75.43% |
| flash-low | Consumer-hidden | 347.1（任务累计） | 256,549 | 180,736 | 3,002 | 70.45% |
| flash-low | Delivery | 912.7（turn累计） | 12,109,797 | 10,769,472 | 9,965 | 88.93% |
| parallel-flashx-high | modeling | 252.6（turn累计） | 2,059,783 | 1,967,488 | 16,861 | 95.52% |
| parallel-flashx-high | coordinator | 435.7（turn累计） | 1,464,435 | 1,413,824 | 25,421 | 96.54% |
| parallel-flashx-high | competency-question | 114.4（turn累计） | 318,365 | 296,576 | 5,305 | 93.16% |
| parallel-flashx-high | Judge | 55.2（留存窗口） | 260,207 | 146,624 | 4,234 | 56.35% |
| parallel-flashx-high | Delivery | 1150.3（turn累计） | 11,882,682 | 10,491,008 | 51,166 | 88.29% |
| parallel-flashx-high | Consumer-public | 115.3（任务累计） | 219,122 | 179,264 | 3,725 | 81.81% |
| parallel-flashx-high | Consumer-hidden | 173.5（任务累计） | 177,371 | 117,184 | 4,322 | 66.07% |
| parallel-flash-high | modeling | 533.5（turn累计） | 1,189,656 | 1,112,768 | 16,313 | 93.54% |
| parallel-flash-high | coordinator | 602.8（turn累计） | 814,914 | 771,264 | 17,351 | 94.64% |
| parallel-flash-high | competency-question | 185.5（turn累计） | 270,959 | 246,208 | 4,582 | 90.87% |
| parallel-flash-high | Judge | 90.3（留存窗口） | 157,291 | 69,760 | 3,779 | 44.35% |
| parallel-flash-high | Delivery | 1913.8（turn累计） | 6,948,099 | 5,519,616 | 47,684 | 79.44% |
| parallel-flash-high | Consumer-public | 49.2（任务累计） | 43,395 | 24,384 | 1,217 | 56.19% |
| parallel-flash-high | Consumer-hidden | 345.2（任务累计） | 214,344 | 151,872 | 4,817 | 70.85% |

公开与隐藏各1个Judge线程；隐藏Consumer每组3个并行线程，表中为累计时间，不是墙钟。低档Consumer表中时间采用任务记录，而token含原生最终响应，两者边界差异保留。

## 旧优化验证与本次明显问题

R4.3-019：数值采集已实际生效，能够从原件复算全部列明角色；但high Consumer快照不完整、宿主／辅助模型及账单缺失，维持完整对账待实测。R4.3-020实际窗口在本次Delivery回执为516800、生产258400；压缩开销仍大，不证明净效果已通过。R4.3-022自主衔接仍未闭合；R4.3-021继续暂缓，本复盘不自行启动压缩改造。R4.3-028的大模型增量感知未被此新建小链覆盖。

### 1. 优先减少Delivery输入膨胀及其压缩开销

| 配置 | Delivery占已知输入 | 两次压缩的输入 | 压缩缓存率 | 占全组未缓存输入 | 决策输入事件数 |
|---|---:|---:|---:|---:|---:|
| flashx-low | 74.0% | 984,777 | 0% | 56.6% | 161 |
| flash-low | 79.7% | 1,052,062 | 0% | 64.2% | 172 |
| parallel-flashx-high | 72.5% | 977,296 | 0% | 55.2% | 160 |
| parallel-flash-high | 72.1% | 1,196,940 | 0% | 68.7% | 164 |

已定位：压缩response_id明确绑定到usage；四组各两次，单次输入约48.8万—70.2万且全未缓存。压缩是总量子集，没有重复加账。Delivery占总输入72%—80%，更值得优先于Modeling微调。高档Flash总输入最低但压缩未缓存输入最高，因此总token少不能推导低费用。

最小建议：沿现有022检查实际decision input及补查原件，减少反复注入的状态正文／无变化快照，保持有业务变化、失败和交接的通知及必要催办。160—172个决策输入事件不是160—172个模型请求，不能只凭事件数删通知。实际重复正文、必要性及可削比例尚未逐条核清；先以现有输入合同做一个有界切口，不新建监控框架。验证看Delivery未缓存输入、压缩子集及完整交接，无授权／质量退步；净时间节省待测。021仍暂缓，不据本报告擅改客户端压缩。

### 2. 明确交接反馈、消除不必要的宿主接管

FlashX low保留的host-supplements记录6次技术补位：provider恢复、额度提醒、query过滤诊断／只读重试、交接指导及最终Host重试handoff；Flash low为补齐freeze和终态后重试handoff两次。成功四题不是自主交付成功。FlashX low把带semantic_roles过滤的no_match误判平台缺陷；去掉可选过滤的同revision只读重试返回matched。反馈中的cq_batch_scope_unauthorized与实际pending-agent条件还造成重复授权请求。

原因已定位到实际过滤含义误解及交接状态解释，provider服务内部原因不推测。最小建议是沿现有读合同和Delivery交接指令纠正解释，返回当前待完成对象／下一动作，保留授权、完整冻结及终态检查；不加新的审批或次数硬门。以同run原地重试和无需Host补位验证，不把所有等待估成可节省时间。

### 3. 验收中的长串行往返值得局部检查

Flash low隐藏批次250.1秒，其中最慢Consumer140.6秒，Judge留存窗口105.4秒；Flash high隐藏批次234.5秒，最慢Consumer176.0秒、Judge55.1秒。FlashX low隐藏批次98.3秒、high115.1秒。Judge输入分别14.0万、39.0万、26.0万、15.7万，低缓存本身可能是fresh线程正常成本，不能视为故障。

Flash low Judge共9个usage事件，FlashX low4、FlashX high7、Flash high5；这是原生usage事件数量，未用作API次数。最小建议：先定位Flash low Judge实际工具纠错与证据搬运，再判断是否可复用现有引用／精简报告。当前仅已定位瓶颈窗口，尚未核清其每次往返的必要性，不直接宣称可删掉105秒或削减验收范围。

### 4. effort先保留结论边界

四题结果相同，本样本low端到端更短；high推理输出明显增加（全组包含Delivery），不能据单次样本判定high无价值或统一降档。建议下一次另获授权时，在相同输入、观察及并行条件下比较low，重点看首次语义正确、返工及完整交付；本次不改模型配置，不启动新运行。

## 证据及限制

原始统计与复算脚本保存在本机gitignored目录：

- [statistics.json](../../../workspaces/retrospective-four-models-20261016/statistics.json)：真实线程、源路径、末次usage时间、分角色数值及压缩response绑定。
- [summarize.py](../../../workspaces/retrospective-four-models-20261016/summarize.py)：只读解析；没有读取凭据或改写运行。
- 每组`workspaces/minimal-chain-20261016-<配置>/authorization.json`及`result.json`：授权、运行绑定、介入与收尾。
- `workspaces/modeling-runs/<run>/runtime/*/home/sessions/`、`evidence/child-sessions/`及Delivery `native/sessions/`：原生回执。
- 各run `acceptance-v3/**/batch-report.json`：8份原始报告均核对full_pass、分母、未执行项和non-blind标记；没有复制隐藏答案回生产。

完整有效语义工时、模型端纯推理时长、供应商账单及计费金额仍unknown。provider-attempt的client_disconnected/200不能直接当限流、失败收费或重试浪费证据，不据此归因。high组授权文件中preparation/未启动字样已过时，实际semantic-start及完成回执优先；本次不改历史运行原件。

本次未运行模型、重验、修改代码／提示或服务；新建议未登记成用户确认项。

## 后续参考基线（用户确认）

用户于2026-10-16确认将本报告统计作为后续参考标准，目的为形成大概量级概念，允许数值不完全准确。后续复盘默认引用本基线比较耗时、token与缓存率，同时披露范围、并行、干预及采集边界差异；不作为性能硬门、精确账单或模型优劣的严格结论。
