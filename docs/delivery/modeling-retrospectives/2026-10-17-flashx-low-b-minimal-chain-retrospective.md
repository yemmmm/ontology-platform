# 2026-10-17 flashx-low-b 最小安装链批次复盘

复盘对象为上一次建模任务：session `minimal-chain-20261016-flashx-low-b`
（授权 `user-20261016-flashx-low-b-three-rounds`，2026-10-16T15:38:10Z 授权，
glm-5.3-flashx low 全角色含独立验收，代码 `e8a06fb` 含 R4.3-029 实现 `841f607`）。
任务 r4-3-026 最小安装链，新 scope／新项目。本批是 R4.3-029 实现后的首个生产批次，
也是 `glm-flashx-low` 档位首次生产使用。台账
[optimization-tracker.md](optimization-tracker.md) 已先读；本报告只读保留证据，
未启动运行、修复或验收。

## 1 轮次核算与终局

| 项 | 值 | 证据 |
| --- | --- | --- |
| 授权 | 3 轮，fresh semantic-start 单列 | authorization.json |
| 消耗 | 3/3；fresh starts 3（15:39:18Z／16:45:35Z／17:36:10Z） | 同上 + 各 run semantic-start.jsonl |
| start2 | PG 5434 连接耗尽，无语义启动，**不计轮**；run 自动 CLEANED、平台项目全删 | launch_incidents |
| 终局 | **全分母 PASS**：公开 mic-concepts pass（full_pass=true）＋隐藏 3/3 pass；cq_verdict=pass，report_digest sha256:47972c2b… | acceptance-v3 双报告 + cq-acceptance-complete.jsonl |
| 收尾 | 18:13:06Z 验收完成即关任务（用户预授权），18:17:30Z 全部临时凭据吊销 | authorization.json / key lifecycle |
| 总墙钟 | 授权→终验 2h35m；→凭据吊销 2h39m | 时间线 |

## 2 完整时间线（UTC）

| 时刻 | 事件 |
| --- | --- |
| 15:38:10 | 授权登记（23:38+08 波谷） |
| 15:39:18 | R1（start1）语义启动；15:39:26 issue-1 provider 限流 → 15:41:11 宿主 recover_provider 恢复 |
| 15:44:37 | 全景评审 cq-review-0001（仅公开题 mic-concepts）宿主 approve；host_action_result 记 `selected_scope_complete: true` |
| 15:45:17 | **freeze-0001：hidden_question_count=0**；9 秒后宿主 freeze-confirm instruction |
| 15:48:32 | Modeling revision 2 封板自查完成（2 Class + 1 ObjectProperty） |
| 16:01:46/16:03:41 | handoff（cq-batch-0001，immutable）；公开验收 PASS（full_pass=true）；但 cq_acceptance_complete 回执 cq_verdict=**fail**——绑定的是隐藏可见性空题集报告（0 题执行） |
| 16:24–16:28 | 宿主 cq_interview 指引补池：slice review 3 题全 approve → freeze-0002（公1+隐3）；但 batch-0002 的 handoff 不可达（batch-0001 已占用 immutable handoff，无 checkpoint）→ **结构死局，R1 报废**；run 停于 WAITING_OWNER（issue-2 挂起） |
| 16:40–16:47 | start2 启动失败：PG 99 条 stale idle 连接（最老 2026-10-13）；pg_terminate_backend 清 97 条；无语义启动不计轮 |
| 16:45:35 | R2（start3）语义启动；正确顺序（全景→interview→切片→单次完整冻结 16:49:01 公1+隐3） |
| 16:49:22–16:52:01 | issue-1 scenario-map projection mismatch，宿主 guidance 3 分钟解决 |
| 17:14:25/17:15:23 | handoff 完成；验收只读 key s3 就绪 |
| ~17:2x–17:3x | 公开验收 **FAIL（judge 标签伪差）**；隐藏 3/3 pass；宿主核对原件后**不调用** complete_cq_acceptance（避免机械封 fail）→ READ_ONLY_WAIT |
| 17:36:10 | R3（start4）语义启动；17:36:54–17:38:17 两阶段评审全 approve；17:38:45 freeze（公1+隐3） |
| 17:38:45–17:53:31 | **冻结后空转 14 分 46 秒**：coordinator 自 ~17:41 起 idle-inquiry ×2；宿主 17:53:17 发 FIFO instruction 告知冻结事实，17:53:31 转达 Modeling |
| 17:54:48 | Modeling revision 2 封板报告（收到指令后 77 秒） |
| 18:04:52/18:13:06 | handoff 完成；公开+隐藏验收双 PASS；acceptance complete cq_verdict=pass |

R3 关键路径分解（语义启动→终验 36m56s）：池+建模 2m35s；**冻结后等待 14m32s（39%）**；
指令→封板 1m31s；封板→handoff 10m04s；handoff→验收完成 8m14s。建模本体在本批不是
瓶颈（R3 建模在冻结前已完成，R1 也在启动后 9 分钟封板）。

## 3 需求验证结论

### R4.3-026 最小业务链（状态更新：部分验证）

- 本批为第二条取得**全分母双可见性独立 PASS** 的最小链新组（首条为 10-16 flash
  新组）。A2 源忠实在本批达标：revision 2 仅 2 个 owl:Class + 1 条 directed
  ObjectProperty，无具名个体／实例断言；10-15 glm-high 组的 A2 失败（具名个体）历史保留。
- A1 精简角色实际采用三轮；A4／A5 材料与分级边界证据保留。
- **自主交付仍未证实**：R1 结构死局、R2 judge 伪差后均由宿主接管推进；R3 冻结后
  空转靠宿主指令解除。完整用量 unknown。
- 需求索引与正文已同步追加（见第 8 节）。

### R4.3-029 职责收敛（状态不变：真实语义／净效率待证；追加有限实证）

- **journal 通道真实走通 2 次**：`request_host_action` → 宿主处理 → `host_action_result`
  追加（`host-results/flashx-low-b-cq-review-0001.json` 宿主窄入口逐题审核并批准；
  `flashx-low-b-issue1-repair-0001.json` 平台问题定性"无平台缺陷、经 recover_provider
  恢复"，含完整证据引用）。F4／F8 的宿主承接面有 live 证据。
- **F1／F2（Delivery 按需流程控制／按需唤醒）live 验证缺位**：Delivery 会话 stdin
  通道死亡（见 P4），round-1 汇报后（最后事件 16:26:40Z）永久等待用户指令，
  round-2/3 全部 host 侧步骤由宿主手动 MCP 执行（submit_cq_review／freeze_cq／
  complete_cq_handoff／start_evaluation／complete_cq_acceptance）。
- 净成本（F9）不可测：Delivery 缺位使本批与四模型基线不可比。

## 4 旧优化项验证

| 编号 | 本批场景 | 结论 |
| --- | --- | --- |
| R4.3-024 | 三轮直接提交、单批原子应用、封板后召回自查（association scan 0 issues）、独立语义全分母 PASS、R3 首试即正确无返工 | 正证据追加；**保持已实现待实测**——"自查发现错误"能力未被考验（三轮首试均正确），更大范围（原 Schema 小链反例）仍待证 |
| R4.3-025 | 三轮单批创建+实际绑定+revision 2；无编译往返返工 | 保持剩余范围待实测 |
| R4.3-013 | body_ref／material_refs 引用交接实际使用（R1 delivery-6/9、R3 delivery-8/9） | 局部采用成立，保持待实测 |
| R4.3-015 | 最小链单切片任务，未触发分阶段早期反馈场景 | 未触发不判失败，保持 |
| RETRO-20261013-09 | 四题含方向题（mic-direction）独立通过，无答案限定类反例 | 保持待调整（原反例未同题复测，不据此关闭） |
| R4.3-019/020/022 | 019 本批未做对账（用量 unknown，Delivery round-1 64 usage events，三轮 team 用量未汇总，可离线复算）；020 未核；022 round-1 决策输入正常 | 均保持待实测 |
| R4.3-028 | 新建 scope，无增量感知场景 | 未触发，保持 |
| R4.3-016 | 本次台账优先、需求核对、逐项定位 | 又一次真实调用证据，保持 |

## 5 已识别问题逐项定位

### P1 R1 过早冻结（hidden=0）→ 结构死局，废 1 轮（已定位，把握高）

- **现象**：15:45:17 freeze-0001 隐藏分母为空；补池后 batch-0002 无法交接（immutable
  handoff 已被 batch-0001 占用、无 checkpoint），R1 报废。
- **原始证据**：cq-freeze.jsonl（hidden_question_count=0）；host-results/
  flashx-low-b-cq-review-0001.json 字段 `selected_scope_complete: true` 及 note
  "……按既有顺序继续冻结/交接流程"；cq-exposure.jsonl 15:44:37（当时仅 mic-concepts
  一题公开）；cq-handoff-complete.jsonl 仅 1 条且绑定 batch-0001。
- **影响**：损失 1 轮额度＋约 60 分钟；且这是**分母完整性缺陷第 3 次跨组出现**
  （10-16 E组"遗漏公开题后过早 final"、10-16 glmhigh-d 新组"过早冻结"、本批 R1），
  前两次复盘记录后未落实纠正动作。
- **原因**：宿主在 host_action_result 中将"全景评审完成"误标为
  `selected_scope_complete: true`（该字段为宿主手写，平台代码无此语义），并授权继续
  冻结；隐藏 3 题当时尚未起草评审（16:24 才补）。Delivery 按新合同（CQ 语义审核移交
  宿主）采信宿主结论后冻结。第一责任面：**宿主侧裁决标准缺失**；第二责任面：
  **runner freeze 入口无分母合同校验**。首层：collaboration/routing（含 platform-contract 缺口）。
- **最小改动**：(a) runner `cq_freeze` 入口校验——任务 profile 声明隐藏题而
  `hidden_question_count=0` 时拒绝或要求显式 override 理由；(b) 宿主操作规范：
  scope-complete 判定必须核对"本任务全部可见性题集已评审进池"方可授权冻结。

### P2 complete_cq_acceptance 绑定空分母报告 → cq_verdict=fail 伪判（已定位，把握高）

- **现象**：16:03:41 回执 cq_verdict=fail，而本批唯一有效公开报告 full_pass=true。
- **原始证据**：cq-acceptance-complete.jsonl（cq_verdict=fail，绑定 freeze-0001）；
  acceptance-v3/reports/cq-batch-0001/attempt-0001/batch-report.json（隐藏可见性，
  full_pass=false，0 题执行）与 public-regression/…/batch-report.json（full_pass=true）
  并存；Delivery 完成报告与 session work_result 均已核对留证。
- **影响**：终局回执与真实结果背离；若无人核对会以 fail 关轮。已作为"技术契约层
  遗留事项"记录。
- **原因**：verdict 计算机械绑定隐藏可见性报告，空题集（executed=0）的覆盖缺口被
  当作语义判负；多可见性报告并存时无显式绑定选择。首层：platform-contract。
- **最小改动**：complete_cq_acceptance 拒绝以 executed=0 的报告作为 verdict 来源
  （或要求显式 visibility／report 绑定参数），空分母返回 typed 错误而非 fail。

### P3 R2 公开验收 judge 标签伪差 → 废 1 轮（已定位，把握高）

- **现象**：R2 公开回归 mic-concepts 判 model-recall-insufficient（FAIL），同轮隐藏
  3/3 pass、同 freeze 同模型。
- **原始证据**：public-regression/cq-batch-0001/attempt-0001/batch-report.json 判定与
  其自身 note（"answer conveys both required definitions and the distinction…
  corroborated by response bb6cd55a"）矛盾；宿主读回平台原件（query_semantic_context
  页含两定义、installed at 方向、非所有权适用性、两个 unknown；get_ontology_read_model
  佐证）。失败层：**acceptance/Consumer-Judge 输出质量**，非 modeling-quality。
- **影响**：损失 1 轮＋约 50 分钟；无 in-run 重验路径（handoff immutable+idempotent、
  S4 续跑需 checkpoint 未启用），只能整轮重开。
- **原因**：glm-flashx-low 档 judge 判定标签与自身依据不一致（观察率 1/4 session，
  样本小）。程序无法可靠仲裁语义判定，但**标签—依据矛盾可检测**。
- **最小改动**（候选，需用户选择）：(a) 验收 CLI 对负向 verdict 增加标签—引文
  一致性检查（负判必须引用具体缺失必答点且与保留响应可对上）；(b) 为判定类失败
  提供一次受控重验入口（限定同 freeze 同模型、结果留证）。暂不修模型档位。

### P4 Delivery stdin 通道死亡 → round-2/3 宿主全手动（已定位，把握高）

- **现象**：Delivery 会话 round-1 正常（含 2 次 request_host_action），16:26:40Z 最后
  事件后永久静默；session.json run_ids 仅 start1、event_cursors 不含 start3/4。
- **原始证据**：session-events.jsonl 尾部（activity=read_only_wait，state=active）；
  台账记载 launch 使用 `tail -f /dev/null` 挂住进程；delivery.py:2483
  `for line in sys.stdin` 是宿主→Delivery 用户席输入通道。
- **影响**：round-2/3 Delivery 完全缺位——R4.3-029 的 F1/F2 live 验证无法进行、
  宿主承担全部 host 侧操作、R3 冻结后空转无人解除（P5）。
- **原因**：宿主手写 launch.py 将进程 stdin 接恒空源，Delivery 汇报后请求"明确的
  用户指令"永远不可达。journal 通道（host_action_result）不依赖 stdin，故 round-1
  正常。首层：runtime/infrastructure（宿主启动配置）。
- **最小改动**：launch 将 stdin 接命名 FIFO（宿主可写）而非 /dev/null；或
  run_delivery 提供文件/journal 输入入口。这是 029 live 验证的前置条件。

### P5 R3 冻结后 14 分 32 秒空转（已定位，把握高）

- **现象**：17:38:45 freeze 回执 accepted 后 team 无人推进；coordinator ~17:41 起
  idle-inquiry ×2；17:53:17 宿主 FIFO instruction 告知冻结事实，77 秒后 Modeling 交
  封板报告。
- **原始证据**：outer-input-receipts.jsonl（cq-frozen accepted 17:38:45.708）；
  idle-inquiry.jsonl（17:46:25／17:51:36，idle_seconds≈300）；outer-instruction.jsonl
  17:53:17；deliveries.jsonl delivery-6/7（17:51:42 coordinator 反向询问）、delivery-8
  （17:53:31 转达）、delivery-9（17:54:48 封板）。
- **影响**：占 R3 语义启动→终验的 39%（14m32s/36m56s）。
- **原因**：旧合同下冻结确认由 Delivery 转达 team；R4.3-029 收敛职责后该动作无明确
  归属，且 Delivery 已死（P4）。宿主在冻结成功后未立即通知（迟约 14.5 分钟，期间
  等 team 自推）。首层：collaboration/routing（流程设计）＋宿主操作习惯。
- **最小改动**：宿主在 cq-frozen accepted 回执后**立即** submit_instruction 告知
  coordinator（零开发）；或 runner 在 freeze 入站时自动向 coordinator 注入确认事件
  （小开发）。

### P6 start2 PG 连接耗尽——根源为残留 run 进程（部分定位，把握中高）

- **现象**：start2 启动即败：PG 5434 连接池满，99 条 stale idle 连接（最老 2026-10-13）。
- **原始证据**：authorization.json launch_incidents（pg_terminate_backend 清 97 条
  idle>30min）；本次复盘发现**105 个 modeling-runs 相关进程至今存活**（最早
  2026-10-13 21:33 启动，与最老连接时间吻合），含 r4009（10-14 启动）的 runner
  FIFO 持有者（python 208093）与 codex agent 进程（208120 等），其 sqlite 心跳仍在写。
- **影响**：损失一次启动尝试＋约 20 分钟；**pg_terminate 只清连接未清进程，连接会
  重新积累，事故将复发**；残留进程同时解释了 r4009 目录 mtime 异常。
- **原因**（推断，把握中高）：历次 run 终局后 agent 子进程与 runner 持有者未回收，
  各自保持 PG 池连接；时间吻合＋进程活性证据支持，未逐进程核对 PG 连接表。
  首层：runtime/infrastructure。
- **最小改动**：对已终局 run 逐个 stop／standby 收尾残留进程（需用户确认后执行，
  部分进程可能属仍待命的会话）；随后观察 PG idle 是否再积累。中期：run 终局自动
  回收子进程。

### P7 宿主外环工具前期误用（已定位，影响小，不立新项）

start1 期间 issue_resolution 三次被 `invalid_outer_input` 拒绝（issue-1 已随
recover_provider 自动结算，无需再 resolve）；issue-2 guidance 提交一次被拒后 run 挂
WAITING_OWNER 未再处理；start3 同类 issue 宿主用 guidance 类型 3 分钟解决，证明已自纠。
start1 run 因此未正式收尾，成为 P6 残留清单一员。

## 6 效率观察（对比四模型基线，不可比披露）

四模型基线（用户 10-16 确认为参考标准，允许量级近似）：flashx-low 组首写 4:39、
至验收 16:02、input 16.38M、cache 89.39%。

本批 R3 至验收 36m56s，约为基线 2.3 倍。**不可直接归因流程**：本批 Delivery 缺位
（宿主手动串行执行 host 侧步骤）、R3 含双可见性验收执行、题池/任务相同但协作形态
不同。可核对的结构性差距：冻结后等待 14m32s（基线组无此空转，因 Delivery 在位转达）。
本批用量 unknown（未完整统计）；判断为正的项：建模本体速度（R3 池+建模 2m35s，
与基线首写 4:39 同量级）、judge 伪差是唯一语义层损耗。

## 7 建议（未确认，仅留存报告；排序按价值）

1. **清理残留 run 进程**（P6）：105 个存活进程持续占用连接与资源，PG 事故将复发；
   需用户确认清单后执行，无开发量。
2. **freeze 入口隐藏分母合同校验**（P1）：分母完整性缺陷第 3 次复发，本批直接损失
   1 轮；小开发，防复发收益确定。
3. **complete_cq_acceptance 空分母绑定校验**（P2）：小开发，消除伪 fail 终局回执。
4. **freeze 确认即时回告**（P5）：先落宿主操作规范（零开发，每轮约省 14 分钟），
   可选 runner 自动注入。
5. **Delivery stdin 启动通道修复**（P4）：R4.3-029 live 验证的前置条件。
6. **judge 标签—依据一致性检查或受控重验入口**（P3）：观察率 1/4 样本小，建议下一
   批次先观察是否复发，复发即需决定性对策；暂不改模型档位。

## 8 本次执行的状态更新

- 需求文档 requirements-v4.3.md：R4.3-026 两条索引行与正文节追加本批全分母 PASS
  （部分验证）；R4.3-029 索引行与正文节追加本批 journal 通道实证与 live 缺口。
- 台账 optimization-tracker.md：R4.3-029 已确认待处理→**已实现待实测**（纠正过期
  状态）；追加本批复盘节。其余旧项维持原状态并补记本批证据。
- 未新增优化编号（第 5 节建议均未经用户确认）；未修改运行原件、冻结池或历史裁决。
