# R4.0-023 独立功能验收

## 需求、范围与边界

复用父 Agent 提供的验收方案及 [权威需求](../../requirements/requirements-v4.0.md#r40-023-独立-delivery-agent-与统一用户交互)、[设计第 9 节](../designs/2026-10-08-r4-0-023-delivery-agent-design.md#9-验证计划与完成门)。本文件为唯一独立功能验收记录，测试者不修改生产代码、不替 Delivery 决定阶段推进。

验收 A1—A12 的核心成功路径、关键反例和必要相邻回归。实际使用离线 native App Server 子进程、FIFO、Runner 和统一业务输入口；用真实操作副作用、收件端、PID/exit/receipt/report 判断，不只静态搜索。A13 没有真实模型/semantic start 授权，本轮明确未验收；功能结论不代表 L0/L1/L2/L3。

非目标：真实 LLM、真实语义建模、后台/前台全套回归、服务重启、冻结历史改写、生产修复、UI、跨机器与自动重启。

## 环境与前置条件

- 仓库 `/home/yangxiang/ontology-platform`；Python `backend/.venv/bin/python`。
- 测试命令从 `backend/` 运行：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest ...`。
- 父 Agent 和两个实现 Worker 同时修改模块；每轮保留版本/工作区摘要。测试者只拥有本文件；临时探针采用 stdin 或临时目录并自动清理。
- 生产实现未就绪的项标 BLOCKED，不能由尚未运行或静态提示代替通过。

## 用例、步骤与期望

| 条款 | 执行步骤 | 期望结果 |
| --- | --- | --- |
| A1 | 启动离线原生 Delivery；实际 tool dispatch；多 turn；统一入口派发 Host 动作并观察结果 | 独立身份与生命周期，动作及真实结果可定位，外层只提供业务输入 |
| A2 | 单/多待答、重复问题、主动纠正、原始多行回答；Runner/FIFO 原文与绑定核对 | 正确消歧与来源，已知事实不重复追问，不伪造 owner answer |
| A3 | 已有 CQ 审核/冻结合同，受委托决定、歧义、修改及过期 digest | 版本及委托依据保持；过期不冻结，历史不改 |
| A4 | 错误 tool/schema/run 绑定后继续正确调用；Runner 可恢复反馈 | 内部返回可操作错误，同会话仍可继续，无业务端技术指令 |
| A5 | 受限 repair 任务通过实际离线子进程 stdin 启动并观察；未授权反例 | 执行者/范围/权限绑定，真实退出定位，进程成功不伪报修复生效 |
| A6 | 请求 submitted/receipt、重复与未知写入；实际只读记录核对及越界反例 | 不盲重放，submitted 不等于 consumed；只读范围正确，无写权限 |
| A7 | 生产终态后继续 Delivery turn；live/S4/public/hidden 入口参数及源状态 | Delivery 不随生产退出，按现有合同串联，有完整新报告绑定 |
| A8 | 新/旧/错误范围报告、证据不足与失败结果 | 不冒用旧报告/未执行 PASS，不改 Judge 裁决，不凭空结果判模型缺失 |
| A9 | 私有 canary、tool catalog、可读目录、公开消息、修复输入边界核对 | 私有内容不通过公共通道流出；修复须独立公开依据 |
| A10 | 暂停/取消、额度/权限拒绝、模型忙或失效时本机中止 | 受影响动作及时停用，不额外 start，受管进程与监督状态准确 |
| A11 | 中断后接续同 session，源进程/未决请求定位 | 先核对记录，不自动重开生产、不双重控制，监督空档真实保留 |
| A12 | 同一材料使用真实用户与测试来源输入并查看代答目录/权限 | 相同输入合同；测试来源可辨，未知可保留，代答无 Host 或私有材料 |
| A13 | 不执行 | 未验收；需另行真实运行授权 |

通过标准：A1—A12 必须逐项获得现版功能证据，无阻断缺陷或关键 BLOCKED；A13 单独保留未验收。固定离线响应只能证明协议/接线和合同，不能证明模型会自主作出语义决定。

## 测试轮次

### Round 1 — 2026-10-08，早期工作区

版本 `825f748` 加并发实现中的未提交 Team 修改，尚未稳定冻结。总体 **FAIL**，发现报告错绑；其他缺口保留，不能据局部通过宣称 A1—A12 完成。

实际命令（从 `backend/`）：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest ../modeling_team/tests/test_delivery_session.py ../modeling_team/tests/test_delivery_runtime.py ../modeling_team/tests/test_delivery_ops.py ../modeling_team/tests/test_r4023_runner_contracts.py -q --tb=short
env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest ../modeling_team/tests/test_host_ops.py ../modeling_team/tests/test_host_ops_s2.py ../modeling_team/tests/test_r3011_cq_lifecycle.py ../modeling_team/tests/test_r4013_semantic_diagnostics.py ../modeling_team/tests/test_r3011_acceptance_cli_flow.py ../modeling_team/tests/test_r4015_public_feedback.py ../modeling_team/tests/test_host_ops_mcp.py -q --tb=short
```

结果：新 Delivery 四文件 **17 passed / 1 failed**（0.69s）；必要相邻合同 **168 passed / 1 skipped**（9.21s）。skip 是 `test_real_judge_raw_verdict_collection`，没有开启真实模型 opt-in；不算通过。实际离线 native 子进程、FIFO 原文及 Runner 收件端、真实 socket 独立验收链、CQ 旧版本、私有边界、receipt/unknown、公开反馈部分和版本漂移通过。

额外 stdin 临时探针：

1. `DeliverySession.call_tool('reconcile_write_state', {run_id:'allowed-run', project_id:'project-wrong', ontology_ids:['ontology-wrong']})`；配置只允许 project-good/ontology-good。结果 `ok:false, delivery_contract, platform read is outside authorized reconciliation scope`，Host 实际调用次数 0（最新实现已正确拒绝）。
2. 在临时 run 上调用 `start_evaluation(...freeze_id='expected-freeze')`，受控 launcher 返回 exit 0；随后唯一新报告填 `batch_id='WRONG-FREEZE', full_pass:true`。`get_evaluation_status` 实际返回 `report_status:'new_report_bound'`，`report_binding.summary.freeze_id:'WRONG-FREEZE', full_pass:true`。临时目录自动清理。
3. Session 恢复/测试身份探针执行时碰到并发编辑产生的 `IndentationError delivery.py:315`，未将瞬态半写文件计入产品缺陷；该探针 BLOCKED，待实现稳定复测。

| 缺陷 | 严重程度 | 复现、期望与实际 |
| --- | --- | --- |
| D01 角色暂不能加载 | 阻塞（在途） | `load_agent_package(ROOT,'delivery')`；应加载，实际 `required_skills is unavailable: modeling_team/skills/delivery/SKILL.md`。已通知父 Agent，该文件随后出现，待复测 |
| D02 报告错绑 | High | 上述 probe 2。应核对本次请求的 freeze/范围并拒绝错误报告绑定；实际把错误 freeze 的唯一新报告绑定为本 operation 的报告，可污染后续交付结果。已请求实现方修复后复测 |

| 条款 | 首轮状态与证据边界 |
| --- | --- |
| A1 | BLOCKED：原生 Thread/tool dispatch 通过，统一完整会话及角色启动仍待稳定版 |
| A2 | BLOCKED：FIFO supplement、Host answer 原文/绑定合同通过；多待答会话行为未完成验证 |
| A3 | PASS（合同层）：既有 CQ 审核/版本/冻结与私有通道；受委托 Agent 原生调用待补 |
| A4 | PASS（合同层）：错误 schema/run/terminal instruction 可恢复，后续工具可用 |
| A5 | BLOCKED：受控 launcher 的 repair stdin/exit/effect_unverified 通过；实际 OS 子进程与会话观察待补 |
| A6 | PASS（合同层）：submitted/accepted/consumed/unknown、重复请求、只读 scope 拒绝 |
| A7 | BLOCKED：native 多 turn、真实 socket 验收与公开反馈合同通过；Delivery 跨阶段统一接线待补 |
| A8 | FAIL：D02；已有 Judge 裁决及漂移/partial 边界通过 |
| A9 | BLOCKED：native 私有事件不公开、CQ/Consumer 包隔离合同通过；最新统一修复/输入路径待补 |
| A10 | BLOCKED：Host 额度/占用/权限边界通过；统一入口忙时取消尚未验证 |
| A11 | BLOCKED：最新恢复入口及监督空档保留待复测 |
| A12 | BLOCKED：最新 test-answerer 来源与输入合同待复测 |
| A13 | 未验收：没有真实运行授权 |

建议：修复 D02、完成正在实现的入口后在本文件追加 Round 2；不修改生产代码或冻结证据。

### Round 2 — 2026-10-08 11:36—11:48 UTC，接线复测

代码仍为 `825f748` 加在途未提交实现。总体 **FAIL**；D01/D03 已解决，D02 部分修复，新增 D04/D05。测试者只读审阅新增实现并使用临时离线探针，未修改产品代码。

实际命令：首轮四文件命令复测 **20 passed**（0.74s）；再加 `../modeling_team/tests/test_host_ops_mcp.py` 的同一命令 **37 passed**（1.19s）。下列探针均为 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python - <<'PY' ...`，从 backend 执行，使用 `TemporaryDirectory`，临时数据/脚本自动删除。

| 步骤 | 实际结果与证据 |
| --- | --- |
| 原生子进程 → DeliverySession → Host → FIFO | 独立 offline App Server 连续调用 get_pending_actions（真实返回 q-1/q-2 两项）、无 ID answer（准确拒绝）、两项合法 answer、主动 supplement、业务 status。实际 FIFO 三封依次为 q-1/text=30天、q-2/text=无法确认、action=instruction/无假问题ID/带 test-answerer source。错误后同 Thread 继续；公开输出仅“已记录业务回答及纠正。”，native 退出 -15。外层只准备合成输入和观察，不调用这些 Host 推进动作 |
| CQ 会话 → Host → FIFO → 真实 foreground admission | 合成 public q1 与 hidden-q 私有 canary；过期 version99 留 cq_review_stale rejected receipt；有效 public/hidden review 留 accepted receipt，决定 note 原文含 delegated/authorization/source/version/逐点理由；freeze 留 cq-frozen receipt 与 digest，public_question_ids=[q1]/hidden_question_count=1；公开投影没有私有题。首次探针直接调用 strict Runner 时遗漏 foreground 对 request_id 的 pop，出现 fields drift，属于探针错误；改用实际 `_handle_foreground_message` 后上述结果通过 |
| 实际 repair OS 子进程 | public task 经 start_repair 的真实 file stdin 传到离线 Python 子进程；PID 1946689 / exit0 / ended_at 实际存在，stdout=STDIN 原文和 TASK_ACCEPTED；effect_verified=false，未伪报修复生效 |
| 实际取消受管子进程 | `_launch_operation` 创建 PID/PGID 1961168 私有进程组，stop_delivery_operation 实际 SIGTERM，最终 status/outcome=stopped，exit=-15，operation record/log 留存 |
| 统一 run_delivery 忙时输入取消 + 接续 | 实际 native fixture 的首 turn 未完成时 stdin 输入“取消”；协议 turn/interrupt=1，取消事件撤回 production/evaluation/repair，输出只有业务状态；EOF exit2 为监督中断。随后 resume=True，仍只有 read/supervise 权限，没有静默恢复预算 |
| test-answerer 与 repair 观察 | accept_user_input 多行未知原文保留；input_role=test-answerer/source_reference 含 test-answerer。resume 恢复 repair operation，observe 实际只调用 get_repair_status，不误用 evaluation |
| D03 监督空档 | `_save(supervision_interrupted, reason=offline, observation={pid:321})` 后 resume；最新 session-events.jsonl 仍保留该条原始记录，当前 session.json 为快照；FIXED |
| D02 wrong-freeze | 错误 batch_id 现在 new_report_rejected/valid=false/summary.full_pass=null；原 claimed true 只保留 reported_full_pass。错误 run_id 仍 new_report_bound/valid=true/full_pass=true，STILL FAILING |
| D04 repair 私有可见面 | 临时 repository 的 `workspaces/modeling-runs/r/competency-questions/private/hidden.json` 放 PRIVATE_REPAIR_CWD_CANARY；public task 明确不读 hidden。start_repair 提供的真实 cwd/env 下离线 repair OS 进程读该文件成功，stdout 含 canary。没有碰现存冻结或真实私有证据 |
| D05 两个活跃监督者 | 第一 run_delivery 进程正常启动，stdin 管道保持打开；第二使用同 session/config resume=True。实际 trace 有两个 thread/start、session-events 两个 ready；两个 wrapper poll 均 None，证明同时存活。两个临时进程组随后 SIGTERM 清理 |

| 缺陷 | 严重程度 | 期望与实际、处置 |
| --- | --- | --- |
| D01 角色暂不能加载 | 阻塞 | FIXED：skill 已落盘，角色加载及四文件通过 |
| D02 报告身份错绑 | High | STILL FAILING：freeze 错绑已修，但 CQ report.run_id=WRONG-RUN 时仍绑定为本次有效报告；profile 名称匹配时其 supplied digest 也未比较，须在有真实 expected digest 条件下继续复验。应核对本次源/model/范围身份，不能把其他运行/模型报告认作本次 |
| D03 监督空档覆盖 | Medium | FIXED：session-events 原记录保留 |
| D04 repair 读取私有 CQ | High | A9/设计修复执行者可见面不满足。期望执行者仅获准公开来源/代码/通用错误；实际 cwd 仓库根包含私有 CQ 和 Delivery 历史。仅有任务中的禁止文字或公开引用不足以证明访问隔离 |
| D05 活跃 session 重复监督 | High | A11 期望原 owner 退出后对账接续；实际同一 session 可同时有两个 native Delivery 进程，未核对当前监督身份/存活。请求实现方补最窄的活跃 owner 核对 |

| 条款 | Round 2 |
| --- | --- |
| A1 | PASS（离线协议/接线）：新 native 实际通过会话派发 Host；自主语义阶段判断留 A13 |
| A2 | PASS（功能合同）：多待答、未知、主动纠正、错误绑定可修正，真实 FIFO 原文及 ID |
| A3 | PASS（功能合同）：真实审核/冻结 admission/receipt，委托理由保留，私有投影隔离 |
| A4 | PASS：新 Thread 错误后成功调用，业务输出不含内部错误 |
| A5 | PASS（进程/任务合同）：实际 stdin/进程退出可观察，生效资格未伪报；授权范围与隔离问题列 A9 |
| A6 | PASS：首轮 receipt/unknown/重复合同与最新 scope拒绝，取消后续启动权限保持撤回 |
| A7 | PASS（合同与生命周期）：native 多 turn 及旧 live/S4/public feedback 路径；不是实际 semanticrun |
| A8 | STILL FAILING：D02 剩余报告错绑 |
| A9 | FAIL：D04；CQ/native/private公开通道已测边界通过不能掩盖 repair 可见面 |
| A10 | PASS（已执行控制合同）：真实忙时 interrupt、真实 child stop、额度权限撤回；不会声称已在途写入被强制回滚 |
| A11 | FAIL：D05；历史和 repair 观察 FIXED，重复监督仍不满足 |
| A12 | PASS（输入合同）：test-answerer 来源明确，输入不获 Host tools 或 native history，未知原文保留；真实用户同入口 |
| A13 | 未验收：无真实模型/semantic start 授权 |

建议父 Agent 让实现方修复 D02/D04/D05，然后在同一文件追加下一轮。既有 168 项相邻证据未变化者复用；新改动仅复测受影响边界。

### Round 3 — 2026-10-08 11:48—11:54 UTC，修复与私有边界复测

总体 **FAIL**，D02/D04/D05 已针对实际原反例修复；新增 D06 私有读取阻断与未决请求发现缺口。`825f748` 加并发工作区，代码尚未提交。新 Delivery+Host MCP 五文件 **37 passed**（0.89s），没有扩成全量。

仍复用上一轮 stdin/Python 临时探针；主要结果：

- **D02 FIXED**：正确 run_id=r 的同形报告 new_report_bound/valid=true；WRONG-RUN 为 new_report_rejected/valid=false/run_id_mismatch；wrong-freeze 仍拒绝。在临时库复制当前真实 openai-sol-medium profile，expected digest=`b62f9a3910cd8b5d21e47abb6c8d64b7365620c31a3162b74f8e1bdd5b3cc37d`，报告 supplied digest=sha256:WRONG 被 model_profile_digest_mismatch 拒绝；无有效 full_pass。
- **D05 FIXED**：实际两个 wrapper 测试，first 活跃，second resume exit1，准确 `this Delivery session already has an active supervisor`。native thread/start 保持1，session.json 字节不变；保留 supervisor_pid=1980409/native_pid=1980414/native_thread_id；first 退出后 third resume 正常启动第二个 native Thread，验证锁既拒绝双重控制又允许接续。临时进程组已清理。
- **D04 FIXED**：新 start_repair 经实际 bwrap namespace 执行离线 Codex 替身，不是只看 argv。PID1989433/exit0，相对私有 CQ 路径和绝对宿主私有路径均 FileNotFoundError，未挂载文件也不可读，公开来源可读、owned 文件可改，admin env 未继承。初版私有 CODEX_HOME ro-bind 导致真实文件写 Errno30，已通知修复；最新再执行 PID1996990/exit0，home 写 runtime.sqlite=OK，私有路径仍不可读，mounted code 的 unowned 文件写报 OSError，原文件未变，owned.py 从 before=True 变 after=True，实际 diff/result artifact 可取。effect_verified 仍 false，不把 fixture 修改当产品修复生效或语义验收。
- 最新支持隔离 Codex 修复；Claude 暂为准确 typed unavailable，无降级成宿主 cwd 执行；真实 provider/auth 能否执行模型留待 A13，不用离线 fixture 宣称已证明。

新反例：在临时绑定 run 放 `control/host-requests.jsonl`，带未决 request_id=UNKNOWN_REQUEST_CANARY，没有 Runner receipt；创建中断记录后 resume。`observe()` 不包含该 ID，read_delivery_artifact(path=ledger) 返回 `delivery_contract / argument should be a str or an os.PathLike object ... not 'tuple'`。

| 缺陷 | 严重程度 | 复现、期望与实际 |
| --- | --- | --- |
| D06 绑定 run 私有 artifact 无法读取 | High | `_read_artifact` 和 `_readback_scopes` 把 `resolve_run_root()` 的 `(run_root,runs_root)` tuple 当 Path。绑定 run 的 CQ/验收 artifact 读取失败，平台 scope 从实际 state 读取同样会 TypeError；approved source 的旧测试未覆盖这个路径。期望能实际读取获准 bound artifact并核对当前scope |
| D07 中断后的未决请求不可发现 | High | 没有 receipt 的 host request 只在已有权威 `control/host-requests.jsonl`；resume observation 没给 ID，artifact allowlist 也不包含该 bound ledger。新 native thread 无法知道应查询哪个 request_id，不能兑现“先对账未决请求、不盲重放”。应允许读取这个既有台账并明确接续先核对，不另建一套状态 |

已报告父 Agent；需修复 D06/D07 后再复测 A3/A6/A11。前轮其他通过证据仅在实现输入未变的范围复用；A13 仍未验收。

### Round 4 — 2026-10-08 11:56—12:01 UTC，数据读取及启动闭环复测

总体 **FAIL**：D06/D07 FIXED，原 D01—D07 均已针对实际反例复验；与父 Agent 追加核对确认 D08 修复核验/部署执行通路仍缺失。不能据已有接线和修复进程通过宣称整个功能需求完成。

实际命令为同一五文件 pytest，最新 **42 passed**（1.58s）；对本轮 Host 可选 issue verification 字段的受影响边界另执行 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest ../modeling_team/tests/test_host_ops.py ../modeling_team/tests/test_host_ops_s2.py -q --tb=short`，**106 passed**（3.28s）。首轮相邻 168 passed/1 skipped 的未改边界继续复用。环境、未授权模型/真实建模边界不变。

stdin 临时探针结果：

- **D06/D07 FIXED**：真实 bound private CQ artifact 读回 PRIVATE_APPROVED_CQ_READ_CANARY 原文与 content_digest；中断后新 session.observe 有 UNKNOWN_REQUEST_CANARY。get_request_result 在 FIFO 已消失且没有 receipt 时 outcome=unknown，建议不要盲重发；实际打开 FIFO 后 outcome=submitted，仍不当 consumed。从真实 state.platform_binding 读出 project_id=p/ontology_ids=[o]。私有读结果未产生 public message。首次断言误把既有合同 outcome 写成 status，属于探针错误，随后按照实际合同复验通过。
- **A1/A7 新 native 启动与生产终态后存活**：独立 offline native Thread 发出 start_run，通过新 DeliverySession 与真实 Host start_run 启动实际离线 OS child（PID2017284），保留 host-supervisor/launch argv/session 引用。child 只创建合成 state=TERMINAL_REPORT_COMPLETE，不执行模型、不写 semantic-start。相同 Delivery Thread 随后调用 get_run_status，实际读到 child pid_alive=false/semantic_start_count=0，继续 emit final“离线启动合同完成；未执行语义建模。”并 finish_delivery。所有调用 ok，子进程仅启动一次。外层只准备 fixture/业务输入/观察，不替 Delivery 调用这些 Host 阶段动作。
- **A8/A9/A11**：此前报告身份、namespace、owner lock 的现版原反例继续通过；scope/私有只读变更未扩大公开消息或修复可见面。
- **A2/A6 request_id 实际入站合同**：新增完整 native submit_instruction → Host → FIFO → `_handle_foreground_message` → Runner → Coordinator → receipt 探针。FIFO 原封带 request_id=native-foreground-request；foreground 按既有合同 pop 后 Runner 输出 instruction-accepted + instruction-delivered，Coordinator 实际收到用户原文一次；get_request_result 返回 outcome=accepted/ack_type=instruction-accepted，receipt 保留 request ID 和 matching digest。验证 actual foreground，未把未经 pop 的直接 receive_outer 调用当反例，也无需扩大 Runner 的业务字段集合。

| 缺陷 | 严重程度 | 证据、期望与实际 |
| --- | --- | --- |
| D08 修复核验/部署无实际执行通路 | High | F3/F8、A5 要求 Delivery 核验修复实际生效后自主续跑，不能外层技术补位。现 native builtin tools 关闭；工具目录没有运行必需检查/受权服务切换/健康核验工具。get_repair_status 提供 exit/tail/定位且 effect_verified 固定 false；diff/result 只有路径与 available，read_delivery_artifact 不允许 `.delivery-ops` 中这些 artifact；resolve_issue(repair_completed) 仅是通知。namespace repair 子进程没有宿主 user bus，不能完成 AGENTS 要求的 backend/frontend 变更后宿主检查/重启/健康核验。应补最窄受授权 Host 核验与必要部署动作、保留准确证据，不给 Delivery 通用 shell、不把通知或 exit0当生效 |

此轮 A1/A2/A3/A4/A6/A7/A8/A9/A10/A11/A12 的**离线功能合同与实际接线**通过；A5 因 D08 仍 FAIL。A13 未验收，真实 provider/auth、自主语义阶段及真实产品修复恢复不从 fixture 结果推断。父 Agent 已决定补最窄 verify_repair 接线，测试者等待就绪后复测，不自行修复生产实现。

### Round 5 — 2026-10-08 12:12—12:21 UTC，异步修复核验与恢复边界

总体 **FAIL**。D08 原缺失通路已增加且实际可执行；发现 D09 未知写入部署门误用和 D10 核验失败无法重试，均为 High，已报告实现方。代码为 `825f748` 加并发 dirty/new 工作区；未启动真实模型、真实 semantic run、真实后端全套、真实服务重启，未改保留冻结证据。父 Agent 授权只用固定命令的离线执行 seam/临时 OS 替身验证部署接线。

实际命令：backend cwd `env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest ../modeling_team/tests/test_delivery_verification.py ../modeling_team/tests/test_delivery_session.py ../modeling_team/tests/test_delivery_runtime.py ../modeling_team/tests/test_delivery_ops.py ../modeling_team/tests/test_r4023_runner_contracts.py ../modeling_team/tests/test_host_ops_mcp.py -q --tb=short`，**46 passed**（1.28s）。另外用同一 Python stdin 临时探针，TemporaryDirectory 中真实 repair child + verification helper 与 PATH 中受控 git/systemctl/curl/python 替身；不修改生产/测试代码，临时进程均退出、目录清理。

| 检查 | 现版真实结果 |
| --- | --- |
| 固定检查计划 | 混合 backend/frontend/modeling_team owned files 通过 execute_verification runner seam，实际捕获 git diff --check、backend pytest、frontend npm build + playwright、Team pytest；授权后固定 unit restart/is-active/8001health/5173health；effect_verified=true 且 semantic_acceptance=not_evaluated。不是运行真实这些套件/服务 |
| 无部署授权 / health失败 | deployment_not_authorized / checks_failed；effect_verified=false，没有伪报生效 |
| unit 所属 checkout | 实际子进程固定 systemctl show 替身返回 /different-checkout，deployment_checkout_mismatch/effect=false；命令记录没有 restart |
| actual async 生命周期 | 核验 helper PID2085930 真实 exit2/checks_failed；另 PID2085978 exit0/verified，process/request/result/log路径与固定命令实际落盘 |
| 取消 | 忙时 git 替身 sleep30，Session取消结束 verification PID2086028，exit=-15/result=None，launch权限退为read/supervise，未伪报核验成功 |
| drift | 已成功核验 owned 文件再变更，verification_status 返回 target_drift/effect=false；resolve_issue(repair_completed)也拒绝旧reference |
| 私有 diff | 实际repair baseline before与owned after生成 `.delivery-ops/repair.repair-result.patch`，Delivery成功读到-before/+after，public message为空；other op artifact拒绝。首次探针误用 workspaces路径而非既有 `.delivery-ops`，更正后通过，属于测试fixture错误 |
| 原issue/证据binding | 有效 fixed-check seam result 的当前reference：wrong issue / wrong reference拒绝；正确原issue-one/reporter=coordinator/control_epoch=7/verificationreference通过Host写真实FIFO，request_id=binding-resolution完整保留；未宣称FIFO提交已消费。另拒绝无repair授权和外session operation |

| 缺陷 | 严重程度 | 实际复现 / 期望 / 证据 |
| --- | --- | --- |
| D09 对账只读 marker 被当部署安全proof | High | 使用实际 Host reconcile_write_state +既有reconcile_write_tail，临时run r的unknown apply_atomic无batch/receipt，返回 reconciliation.blocked=[reason=write_unreconciled]、readback_only=true。Session call_tool仍将r加入reconciled_runs；随后verify_repair启动helper PID2085978并执行固定离线部署命令链，result verified/effect_verified=true/deployment_verified=true。期望 unknown/blocked/scope_drift 不能释放运行时切换门；readback_only只说明没有写权限，不说明写入已对账成功。成功proof当前实现是永久set，新的写尾也不会使它失效；应在实际部署前核对当前boundrun事实 |
| D10 同repair核验失败后不能重试 | High | 首次helper PID2085930因git返回1 =>exit2/checks_failed；临时环境修正git为0，再对同owned repair调用verify_repair，start_verification仅见目录存在便返回旧PID2085930/旧checks_failed，没有新增command或helper。期望保留首轮失败证据并允许同原goal重新核验；检查环境失败或代码drift不能成为需重新派repair才能解除的硬死路 |

D01—D07 原反例现版通过。D08基础接线 FIXED，但 A5/A6/A11 因 D09/D10 尚不通过；其他未改条款复用 Round 4 证据。A13 **未验收**，真实provider/auth、自主语义建模、真实产品部署生效均不由离线 fixture 推断。建议修复 D09/D10 后只复测本轮反例及受影响核验/恢复边界。

### Round 6 — 2026-10-08 12:23—12:29 UTC，最终独立功能复测

总体 **PASS（A1—A12 离线功能合同与实际接线）**。D09/D10 对原反例及受影响边界 **FIXED**，D01—D10 已无未关闭阻断。A13 **未验收**；本结论不等于真实模型自主交付或 L0/L1/L2/L3 PASS。工作区 HEAD 仍为 `825f74811d51baff5d770b3d60e8b51defef883e` 加本轮并发 dirty/new 实现；父 Agent 后续仅声明文档/docstring/Ruff整理，不把测试者未验的后续语义变化算入本轮。

执行同 Round 5 的六文件 focused 命令，新增永久回归落盘后 **48 passed**（1.54s）；此前原版同命令 46 passed（1.26s）是本轮修复初始快照记录。未重复全 Team/backend/frontend全套，未真实重启。对未变相邻边界复用前轮已执行证据。

独立 stdin 探针采用真实临时run state、既有 submission-intents 文件、只读本地 HTTP endpoint（只返回合成 batch listing）、真实 repair/verification OS 进程、固定 PATH 命令替身。没有真实 LLM、平台mutation、semanticstart、业务模型修复或冻结证据变更。

| 反例/回归 | 现版证据与结论 |
| --- | --- |
| D09 初始未知写入 | unknown apply_atomic/no receipt 的真实 intent 及 HTTP readback返回blocked，reconciled_runs不缓存成功；verify_repair 返回 current write reconciliation is blocked，**没有创建helper/attempt**；FIXED |
| D09 旧对账失效 | 空tail对账先得到成功set，再写入unknown intent。verify重新查询HTTP并拒绝，set清除；不复用旧成功，FIXED |
| D09 长检查后新unknown | verify启动时tail空；实际fakepytest检查时写入unknown intent。helper PID2107681 exit2/status=write_state_unreconciled/effect=false；result有blocked=write_unreconciled，日志只有git/pytest，没有systemctl/restart。证明子进程在检查后部署前再次读取当前tail/live readback；FIXED |
| D09 scope drift | actual HTTP ontology listing出现foreign-session batch，verify拒绝，未创建新attempt；PASS |
| D10 同op失败重试 | attempt1 PID2107572 exit2/checks_failed；修正临时git后显式verify，同op attempt2 PID2107576 exit0/verified/effect=true；attempt1目录每个request/result/process/log文件字节保持完全相同，current指向attempt2；FIXED |
| D10 PASS/漂移/活跃重复 | 当前PASS再次verify保留attempt2/PID；owned文件变更令旧PASS target_drift，再verify得到attempt3 PID2107606/exit0/verified；活跃attempt重复verify不产生新PID/attempt；PASS |
| 取消新attempt | Session取消实际核验 PID2107691 =>exit=-15/result=None，确认 ownership使用当前attempt的真实request路径；PASS |
| request scope/身份 | request实际包含run_id=r/project_id=p/ontology_ids=[o]；helper和Session HTTP读取真实绑定scope。旧attempt reference不等当前record；无权/异op/异issue/wrongref边界复用Round5并经当前绑定路径复核 |
| 新 native核验到原issue恢复链 | actual offline AppServer→DeliveryRuntime→DeliverySession 调用verify_repair、重复get_repair_verification_status观察真实PID2116473/exit0、resolve_issue、emit_user_message；同Thread8次工具调用全部ok。实际FIFO收到issue-native/reporter=coordinator/control_epoch=8/request_id=native-repair-resume，verification_reference准确指attempt-1/result.json。公开仅业务文本“修复检查已通过，已请求恢复原步骤；语义验收尚未执行。”；不是提交已消费或原业务步骤已语义成功的断言 |

最终条款矩阵：

| 条款 | 独立结论 | 证据来源与边界 |
| --- | --- | --- |
| A1 | PASS | Round2/4 actual native独立Thread→Host start_run→真实离线child→终态后继续工具→final/finish；自主语义决策留A13 |
| A2 | PASS | Round2多待答/未知/主动补充原文与来源/错误后可继续；Round4 native→FIFO→actual foreground→Runner→Coordinator→receipt |
| A3 | PASS | Round2实际CQ审核/版本拒绝/委托理由/公开与隐藏冻结边界；Round4绑定私有产物真实读取 |
| A4 | PASS | 原生错误调用后同Thread成功工具；Round6检查失败可显式重新核验，不永久杀死原目标 |
| A5 | PASS | Round3实际隔离repair写owned文件/真实diff；Round5/6固定异步核验、权限/健康/漂移否定路径、native恢复原issue完整FIFO binding；真实产品生效留A13 |
| A6 | PASS | request unknown/submitted/accepted和receipt；native真实入站pop request_id；Round6真实unknown写入两次live对账阻止部署 |
| A7 | PASS | 源终态不结束Delivery，现有live/S4/public/hidden入口必要相邻回归及新报告严格绑定；没有真实semanticrun |
| A8 | PASS | D02 wrong-freeze/wrong-run/wrong-modeldigest均拒绝；旧报告不冒用，partial/证据不足不伪报full_pass；不改Judge历史 |
| A9 | PASS | Round3真实bwrap namespace私有relative/absolute不可读、仅获准source/ownedcode；native/public消息隔离，修复仅有合法公开输入；私有diff读取不公开 |
| A10 | PASS | Round2忙时native interrupt、实际child stop与权限撤回；Round6实际verification取消且不伪报effect |
| A11 | PASS | append历史监督空档、实际双wrapper owner拒绝/退出后resume；unknownledger发现/receipt先核对；Round6每次核验及部署前重新对账 |
| A12 | PASS | user/test-answerer同输入合同、原文/来源/unknown保留；代答仅业务输入，无native history/Hosttools/privatemount |
| A13 | 未验收 | 没有真实建模/LLM授权，offline脚本证明接线，不证明Agent会自主决定语义阶段或真实独立语义结果 |

独立实现只读审阅最终结论：**0 Critical / 0 未关闭 High**（当前明确范围）。审阅依据为权威 F1—F8/A1—A12、新 Delivery/runtime/Host ops/verification 的实际调用与相邻合同、CLI入口与role/model/tool权限面；不以开发者自测替代上表独立结果，也不声称GitNexus图级覆盖。旧D02/D04/D05/D06/D07/D08/D09/D10均保留首轮缺陷及现版原反例修复证据。没有依据要求额外安全框架、全量套件或新治理机制。

建议父 Agent按本轮实现快照接受独立功能结果，保持A13和真实语义阶段未验收。若其后发生验证语义、调用合同或可见面变更，须只复测受影响边界；文档/docstring/Ruff格式整理本身不重开已验证语义路径。
