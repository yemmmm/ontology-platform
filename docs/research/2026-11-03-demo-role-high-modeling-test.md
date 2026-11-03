# Demo 专职多 Agent 建模测试

日期：2026-11-03。目标：验证 R5.0-012 真实角色采用及完整 Demo 建模质量。

使用 scripts/modeling、role-team/v1，全部托管角色 glm-direct/glm-5.3-flash/high；独立 3 CNY 预算，过程评价 cq/slicing/integration 开启，完整模型独立评价另行执行。新项目不继承旧模型或 PASS。来源复用上一轮冻结的 Demo 原文、API、Schema、公开 CQ；36 项独立标准保持原文，生产不可见。

需求来源：[R5.0-011/012](../requirements/requirements-v5.0.md)；[启动合同](../../skills/modeling-dev-loop/references/v5-runbook.md)。输入与授权：workspaces/v5-runs/demo-role-high-20261103-inputs；运行：workspaces/v5-runs/demo-role-high-20261103-start1。

状态：已准备启动；角色采用、过程评分、生产自查与独立 L1 结果分别取证。公开 Demo 不代表客户业务盲测或 L2 重复性保证。

## 首次真实采用与第一阻塞

代码基线 `0d0272e`。Modeler 首个原生 turn 于 2026-11-03 15:36:13 UTC 启动，随后实际全文读取五份材料并保存 29 条业务命题及 U1–U12 未知，Coordinator 使用另一原生线程。输入准备时预算创建 Python 的导入路径错误，先行 start 因 budget_unavailable 未启动模型；Host 补齐既有账本后沿原 run resume，未新建 start。

第一阻塞为 role_scope_basis_changed：Coordinator 首两回合将新发布范围材料填入输入 basis.scope_ref，而当次输入仍为 null。Modeler 随后也使用尚未接纳的范围引用触发同类反馈。原始产物保留，未写入实际模型。Host 通过 input 仅解释输入基线与新产物的技术区别，没有修改业务候选或提供验收答案；此项属于 prompt-contract/协作合同采用缺口，不能据此评判建模质量。T0：基线校验保护输入版本正确性，应保留；当前错误可通过准确反馈修正，不是永久拒绝。

首版切片方案固定引用 `coordinator-scope-plan-v1` rev1，过程评价绑定 b432da7cd3db6424552720cd74dd1b164a25ece33acfd32dd591a4cbce02a3da 已完成，结果 satisfied、无已证实缺口。此处只评方案，不证明方案已被程序接纳、实际应用或 L1 通过。CQ 专职已实际启动，尚待正式成果。

## 有界失败收口

Coordinator 第三回合回显基线正确，但因本回合未实际重读来源得到 source_read_missing。Host 前述“不要重读未变内容”的建议与当前 per-turn 校验不兼容，已公开更正。第四次提交读取来源后，结果被保存，但安装 scope 时因 assignments 包含既有 cq-public 得到 work_unit_identity_conflict。`role_team.ASSIGNMENT` 允许该 role，而 `role_work._install_scope` 拒绝保留 cq-public 身份；正式范围未安装，Modeler 仍停在 source_intake，未进入可执行候选建模。此项属于 platform-contract / prompt-contract 交界，不能归为模型质量差。

费用约用至一半仍未形成实际模型，Host 发出 stop 进行本轮失败测试收口；自然停止请求返回 waiting_for_turn_end，尚有 Coordinator 与 CQ 在途，不能将请求接受记为停稳。已开始回合允许自然结束，不再启动额外生产/评价调用。此处未追加预算、未更换模型、未改写候选、未修改平台代码。

CQ 过程评价绑定 685738b1242dd91108b68d974857a2053905f94d4ecc01cae7a8b258c592b72b 已完成，satisfaction=gaps。goal_coverage 与 conditions_and_cross_unit_questions 均 3 分/low，clarity 与 source_fidelity 均 4 分/none。缺口涉及管理操作不变量、停用凭证的新调用/回放及重启用不补额、Q10 回放与冲突分支等。评价仅针对公开 CQ 固定成果，不证明实际模型缺失。切片 satisfied 与 CQ gaps 不能合并成整体 L1 PASS。一次 CQ 提交误复用切片 goal，仅留 queued 未执行；随后按准确 CQ scope/goal 重提交并执行，不把误提交当有效评分。

当前结论：R5.0-012 真实专职上下文/作者/来源分析及部分阶段成果已经采用，但生产分派→候选→整合→应用读回未走通，完整需求 PARTIAL，本轮 L0 链路 BLOCKED；L1 建模质量未验证，L2 未执行。

## R5.0-012 验证范围

| 要求面 | 本轮证据 | 状态 |
| --- | --- | --- |
| F1/F2 专职身份、模型绑定、独立上下文 | Coordinator、CQ、Modeler 原生执行及署名成果；过程评价另立上下文，全部 high | 已观察采用，完整生产分工未闭环 |
| F3/F5 范围、渐进交接与消费 | intake 先开始，CQ 后续实际执行，精确材料发布/读取；范围安装被拒 | PARTIAL/BLOCKED |
| F4 公开 CQ | 复用 Q1–Q9、新增 Q10–Q12 draft、保留未知；独立过程评价 gaps | PARTIAL |
| F6/F7 整合、共享定义与跨候选 | 仅有方案，无可执行候选与实际应用 | 未验证 |
| F8/F9 局部重入、治理自查、整体交接 | intake 技术纠错保留；无实际模型，不能验证应用后闭环 | 未验证 |
| F10 可恢复反馈 | 保留原 run，字段反馈后可纠正；范围身份冲突暴露新阻塞 | PARTIAL |
| F11 控制、时间与费用 | 首次来源分析及时启动；金额账本与自然 stop 有实际回执 | 收尾核对中 |
| F12 新入口与冻结合同 | scripts/modeling 与 role-team/v1 默认专业包/工作树接线 | 新任务采用，不外推兼容性 |

停止前平台快照 `b040d0ec19684a8e9ad9ec1638917a89`：Project `a237002d-38c1-44ec-8e3d-fb094f2617c9`，Ontology `dbc6dd64-08c5-4a8a-bb2c-5a0795a26cee`，revision 0、resource_bindings/resource_refs 均空，model_read_error=null。snapshot object_count=46 是工作空间对象数，不是实际模型资源数；快照读取密钥已撤销。

## 最终状态、费用与资源

停止后两在途回合均自然结束，control.mode=stopped、status=settled、active={}。最后 Coordinator 回合仍以 role_material_not_consumed 拒绝：声明消费新版 Modeler 移交材料，但本回合该引用实际读取字符数为 0。CQ 最后为 public_cq_seed_invalid：本轮复用的 public-cq.json 是 ontoweave-custom-cq-seed/v1，当前专职刷新代码按 validate_snapshot 校验，存在来源形状兼容/准备缺口。原始错误均保留；不以终态后继错误覆盖首次基线阻塞和范围身份冲突。

自然停止后未再 resume，1 次 fresh semantic start、1 轮初建（未实际修模）、12 个真实托管执行：Coordinator 5、Modeler 3、CQ 2、过程评价 2。没有进入可执行候选/应用/治理读回，36 项正式模型评价没有启动，整合过程评价未观察。过程汇总最终 production_status=failed；较早 closed 仅是汇总标签，不能当业务完成，旧版本保留。

原生模型执行窗口：2026-11-03T15:36:10.357000+00:00 至 2026-11-03T16:24:24.803000+00:00，2894.446 秒（48 分 14 秒，含工具/供应商等待及纠错）。授权首次落盘 15:35:35 UTC，清理完成约 16:24:36 UTC，落盘至清理约 49 分钟；精确用户授权到达与 Host 有效劳动时间未完整计时，不冒充总任务精确墙钟。各角色原生区间并集相互重叠，不能相加作总墙钟，更不能当纯语义推理劳动。

| 角色/用途 | 输入 token（含缓存） | 输出 token | 原生区间并集秒 |
| --- | ---: | ---: | ---: |
| competency-question | 629485 | 64422 | 1199.415 |
| modeling | 1200445 | 70553 | 1026.95 |
| process-evaluation | 71669 | 31311 | 769.077 |
| coordinator | 1036701 | 124099 | 2574.359 |

合计输入 2938300，其中缓存输入 2297856，输出 290385，输入加输出 3228685 token。12/12 托管线程原生累计用量已知；按线程末次累计统计，未累加中间累计样本。外部 Host 与未接线辅助调用用量 unknown，单列且不计预算；全任务计量仍 PARTIAL。

冻结价表估算费用 1.84794112 CNY，预算余额 1.15205888 CNY，未追加。known=12/12、unknown=0、provisional=0、inflight_count=0、pending_settlement=0；账本 tail_bound 仍保留过时的 inflight/unknown 组件，本轮不顺带改账本，不能以此当当前仍有原生执行。价格为本地估算，不是供应商账单。

cleanup-final.json 确认 scope_disposition=deleted-empty：本轮空项目/本体已删除，关联 Session/Lease/项目 key 无残留，protocol_key_revoked=true、admin_key_revoked=true、aggregate_keys_non_active=true；快照与原生失败证据、工作空间及预算均保留。旧测试项目不受影响。

关键原件：inputs 下 authorization-and-scope.json、task.json、process-slicing.log、process-cq.log、process-summary-failed-final.json、status-final.json、observed-usage-summary.json、budget-final.json、cleanup-final.json；run 下 executions、semantic-starts 与 snapshots。只新增本研究记录，未修改平台实现，无需运行前后端套件或重启服务。
