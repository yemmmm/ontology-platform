# R4.3-015 成功写入信任边界与既有切片反馈设计

## 1. 范围、授权与基线

权威范围：[R4.3-015](../../requirements/requirements-v4.3.md#r43-015-分阶段建模反馈与成功写入信任边界)。
用户已确认 D1—D6，并在后续讨论中确认：小链通常复用已有业务切片，早期 Consumer CQ
反馈已有实现，本条是既有流程上的局部调整。2026-10-12 本轮授权详细设计及独立审阅，
不含开发、外部模型调用、真实建模／修复／验收运行或额度消耗。

静态代码基线为 `main@246bd03`，设计开始时工作树干净。独立设计审阅 Round 1 PASS，
0 Critical／High，无未决关键假设；
审阅过程保存在[设计审阅记录](../records/2026-10-12-r4-3-015-design-review-record.md)。
设计 PASS 不等于实现、独立功能验收、真实业务质量或提速 PASS。

本设计的实际增量：取消成功 apply 后例行全量／逐条写入核验的后续要求；同步执行回执、
工具说明和活跃提示；沿现有协作安排公开反馈的有界提交暂停；明确已应用与质量已验证的
不同含义。复用切片、场景地图、候选／计划审核、连续执行、公开反馈和最终独立验收。
不增加小链目录、阶段资源、平台接口、数据库字段、角色、锁、调度器或通用状态机。

## 2. 当前能力及最小差异

| 当前入口／要求 | 已有能力与问题 | 本期调整 |
| --- | --- | --- |
| `runner.py::_handle_execute_approved_plans` | 当前版本 dry-run、原子 apply、Attempt 证明、版本确认及不重放；成功后仍返回 `pending_protocol_governed_read` 并要求完整资源／关系读取和关联扫描 | 保留执行完整性；把成功返回的资源读取状态改为中性的 `not_evaluated`，后续动作按业务目的读取及最终自查 |
| `capability_mcp.py` 的工具清单说明 | `protocol_execute_approved_plans` 说明要求实际资源读回跟随 apply | 与新返回含义一致；输入 schema、工具名、挂载和能力授权保持 |
| Protocol 活跃指令 | 成功后逐条核对批准 SPO，并把全量分页／关联检查安排在小链交接前 | 取消当前 unified CQ 路径中的逐批写入核验；业务读取、必要异常定位及最终关联检查保留 |
| R4.3-004 角色／方法提示 | 已完整小链可先执行，已有公开反馈入口；但触发条件仍写成先完成实际资源读回 | 改为阶段覆盖及依赖具备、明确成功应用后可消费；优先沿现有切片推进 |
| `public_feedback.py`、`__main__.py::_run_public_feedback` | 检查点／公开题选择、Consumer 实际读取、前后模型及整轮写尾绑定；变化返回 `superseded` | 保留代码及错误合同，以现有消息安排无新提交的读取窗口；不实现更细并发绑定 |
| `delivery.py::DeliverySession._read_artifact` | 允许 bound run 的 evidence／acceptance-v3 等正文，遗漏 early-feedback；`get_evaluation_status` 仅返回报告状态及数量摘要 | 沿原读取工具加入绑定运行的 early-feedback 目录及保留响应；Delivery 核对当前 operation／报告摘要后消费实际公开正文 |
| R4.0-024 关联自查、R4.3-014 恢复 | 已有实际关联扫描、业务处置、受影响复查及原 Attempt 恢复 | 继续复用；不把最终关联检查提前为每批应用的完成门 |

范围及完成含义的决策主表保留在权威需求 D1—D8，不在本文复制另一份完整决策记录。
D1／D4 沿用既有能力及本轮确认的使用方式；D3 是主要代码／提示差异，D5 是协作约定。

## 3. 生产与反馈顺序

1. Coordinator 保留完整获准范围、已有切片、共享定义、依赖及未完成事项。Modeling 优先
   选择一个可消费切片；切片过大或真实问题跨切片时，再按实际依赖组织阶段。没有独立
   的小链模型或固定阶段数，不要求先完成全局详细候选／计划。
2. Modeling 形成当前阶段的完整候选及未知；Protocol 转换为依赖有序的实际计划。
   Coordinator／Protocol 复用当前候选内容和翻译审核、`protocol_check_plan_coverage`。
   当前阶段必要定义、关系和依赖漏项时先补齐；全局剩余范围继续由地图保留。
3. Protocol 向 `protocol_execute_approved_plans` 交当前阶段的完整获批 `plan_refs` 列表，
   该列表按真实依赖和现有批量上限形成。工具不在执行中重新分片，不要求 Agent 在一份
   未结束的连续调用中插入反馈；下一次反馈安排在实际调用返回、阶段已明确应用后。
4. 工具仍依次取得当前版本、有效 dry-run、apply 和版本确认，并保留每个 Batch／Attempt
   原身份。明确成功后可继续获准工作；不再追加逐项写入比对。阶段应用和语义反馈分开记录。
5. 首个可消费阶段尽早通过既有公开入口取得少量 CQ 反馈；后续由 Agent 按价值判断。
   开始和结束协作见第 5 节。反馈 Consumer 只读取平台，宿主沿公开题意定位不足；该入口
   不调用最终 Judge、不消费正式 acceptance attempt、不发布 production handoff。
6. 发现问题后，暂停真实受影响内容及其依赖。Modeling 修订，Protocol 复用审核及
   dry-run/apply；复核受影响公开题及关联。其他工作可继续，但不能把未解决项记为通过。
7. 全部范围收口时核对覆盖及共享一致性，执行 R4.0-024 实际关联自查、业务处置和必要
   修正；生产角色保持可接收反馈至该检查完成。再沿现有写入排空／只读交接进入完整
   独立 Consumer／Judge 验收，最终分母、未知和隐藏隔离保持。

## 4. 执行回执合同（D3／D7）

### 4.1 保留的执行证明

不改变 `plan_ref`、projection digest、当前批准、lease、有效 dry-run、Batch／Attempt、
幂等键、请求内容、回执保存及 `version_readback_ref` 的来源。`get_modeling_context` 的
模型修订号用于执行版本确认；其计数不证明资源内容、SPO 数量、语义覆盖或业务正确。

`staged_batch_write_forwarder.py::_forward_write_with_readback` 的受控
`get_modeling_batch`／Attempt 身份及终态核对保留。它是工具内执行确认，Agent 不需要
因已取得同一证明再读取资源清单或自己重复确认同一 Attempt。

### 4.2 返回值的最小变更

| 执行结果 | 返回与后续行为 |
| --- | --- |
| 本次明确 `applied` | `completed[]` 原应用／身份／版本证据保留；单项和顶层 `resource_readback_status="not_evaluated"`，`semantic_verdict="not_evaluated"`；`COMPLETE` 只表示本次获批列表执行完成 |
| 同计划／digest 的已应用结果 | 沿原证明返回 `already_applied`，不重放；资源读取状态同样为 `not_evaluated`，不创造再次核验任务 |
| `mode="dry_run"` | 保持 `validated`、`resource_readback_status="not_applied"` 及后续审核／apply 授权要求，不能提升为已应用 |
| 中途执行、版本确认或引用失败 | 保持 `PARTIAL`、此前完成项、具体 `error.stage/plan_ref/reason_code` 和原恢复路径；不把失败改成成功或把已应用内容当成未应用 |

成功 `required_next_step` 改为：沿真实依赖继续；在有价值节点取得公开业务反馈，并在
整轮生产交接前完成必要全局／关联检查。它不再要求每批完整分页读取及关联扫描。
不使用 `resource_readback_status="complete"` 或 `semantic_verdict="pass"` 代替未执行的读取。

保留已有返回字段、采用中性状态是 D7 的技术落实；不增加第二套布尔值、结果版本、
兼容适配层或 HTTP API。当前调用点检查表明该字段由 Runner 返回、活跃提示解释并由
`test_v43_production_refs.py` 断言，未发现生产代码按其值打开交接门。
`acceptance.py` 仍经同一 capability handler 返回结果，输入合同和授权校验不变。
旧回执／检查点／测试历史原样保留，不回写旧状态；新冻结基线使用新的说明及返回合同。

### 4.3 异常与完成门

`applied` 必须属于当前计划／请求，只有 capability `ok`、HTTP 接收或 apply 意图不够。
缺失或非终态 Attempt、超时及断线仍按原身份恢复；不得换 key 整体重放。若已应用证明
存在但后续版本确认失败，保留失败及原证明，沿已有入口重取必要元数据，不重新 apply。

真实业务读取发现漏写／错写时定位平台缺陷，保留原状态及实际读取，沿现有不确定写入／
完整性合同处理。不得因此给每次成功写入新增常驻全量检查。本设计不改变 R4.3-014
的恢复覆盖判断、原 Attempt 延续或受影响 Ontology 隔离。

`resource_readback_status` 当前不是 runtime 硬门，本期不删除实际语义读取校验来配合新值。
现有 formal ticket／ordinary retrieval 的独立合同继续使用其原始证据要求；当前 active
unified CQ 路径的最终 R4.0-024 扫描及完整验收保留。`terminal_report_blocked` 等既有保护
不因正常成功不重复核验而统一关闭；实施时核对当前路径是否发生真实拒绝，再按 T0 处理
证据指出的窄失败，不预先修改恢复、Runtime guard 或旧 formal 交接。

## 5. 公开反馈提交窗口（D5）

本期以现有消息和回执协作，复用 `public_feedback.py` 的写尾及前后绑定检查。

1. Delivery 通过已有 `submit_instruction(kind="delivery_guidance")` 向 Coordinator
   说明本次反馈范围及暂不提交新 dry-run/apply 的要求，沿原授权／来源引用发送。
   Coordinator 向 Protocol 发有回复要求的既有 Team 消息，确认停止安排新的提交。
2. 已在途的连续计划调用先正常返回；不强制中断，不能从“指导已接收”推断提交已排空。
   Protocol 返回实际完成／未确认情况。Delivery 核对当前 pending、提交回执及检查点
   `write_positions`，未确认写入按原恢复合同处理。候选分析和计划准备可以继续。
3. 确认无在途／未知提交后，复用当前完整 `materialization_progress` 检查点；缺少时沿
   已启用的保存入口取得实际发布回执，不改变运行 Task，不要求最终 handoff。
4. Delivery 经现有 `start_evaluation(mode="public-feedback")` 和
   `get_evaluation_status`，或获准 manual Host 的原 `public-feedback` 入口取得反馈。
   窗口覆盖开始前观察、Consumer 读取及结束后绑定核对；不只覆盖发起调用的时点。
5. 原 operation 的实际终态证明反馈任务已结束后，
   无论结果为 observed、partial、superseded 或不可用，都经
   同一 guidance／Team 通道解除本次正常提交等待，继续受影响修复或无依赖工作。
   实际 unresolved write 或用户暂停仍遵循原约束，不因反馈结束自动解除。已有 Consumer
   owner 原地待命不代表任务未结束，不以保留进程退出作为释放条件。
6. 调用超时或返回丢失时，沿绑定的原 evaluation operation 查询状态及保留报告；无法
   确认任务已结束时保留具体待办，不启动第二个反馈或擅自释放提交窗口。原任务结束后
   恢复正常推进，显式 stop／暂停由用户及原生命周期合同控制。

当前 public-feedback 不创建 retained `.owner`，因此 `work_state` 可持续显示 `working`。
按 `delivery_ops.py` 的 reaper／状态回执核对原 operation：`status="exited"` 且有实际
`exit_code`／`ended_at` 可证明该公开反馈 CLI 已结束；非零退出也结束窗口，业务结果
仍按实际报告记 partial／未执行。具备 owner 的现有路径另沿其 `task_closed`／任务封口
回执核对，不等保留 owner 退出。有效 report binding 用于证明当前业务反馈资格，报告
缺失或绑定被拒绝不抹掉已确认的 operation 结束事实；unknown write／用户暂停仍保留。

指令、确认和结果复用已有消息 identity／reply 绑定，不增加 feedback-window 资源或
平台写门。跨运行或外部写入仍可能导致漂移，现有 `superseded` 校验继续兜底；本期不
承诺并发隔离。过期结果保留原义，重验只在新的有效状态上进行，不混用前后证据。

### 5.1 Delivery 的反馈正文读取（D8）

`get_evaluation_status` 已返回本次报告的 path、digest、valid 和状态／题数摘要；该摘要
不含 Consumer 答案或读取正文。当前 `_read_artifact` 的 bound run 白名单缺少
`early-feedback`，因此纯提示不能完成独立 Delivery 的反馈消费。本期仅在该已有工具
允许目录集合中加入 `early-feedback`，沿同一 run 绑定、普通文件及大小限制返回原文和
content digest；其内实际平台响应仍属于同轮公开反馈，其他运行及任意 host 路径不开放。

Delivery 从原 operation 的有效 `report_binding` 取得报告定位，用已有正文工具读取
`feedback.json`，将返回 content digest 与绑定 digest 核对；再按正文的保留响应定位读取
公开问题所需证据，路由可定位缺口。旧报告、digest 变化、绑定被拒绝或超出既有读取限制
时保留不足，不用题数摘要证明业务已反馈或补造答案，不额外建设分页／摘要服务。
解除提交等待看原 operation 是否结束；即使报告不足，任务确认结束后仍可依 D2 继续
安全工作，反馈质量记为未完成。report 是否可用于业务判断与任务是否仍在读取分别处理。

## 6. 指令、方法与完成表述对齐

- Protocol：将当前 unified CQ 路径“每次 apply 后核对全部批准 SPO”“执行完成后必须
  全量读回并扫描才可小链交接”等要求替换为第 4 节。保留分页完整性、实际 SPO 判断、
  业务读取及异常证据的正确性规则；不删除旧 formal 路径的独立交接合同。
- Modeling／Coordinator：复用现有切片、当前候选／计划覆盖及共享身份。首链公开反馈
  不再等待例行资源写入比对；问题按实际依赖修正，当前阶段已应用不提升为业务 PASS。
- Delivery：按第 5 节安排并结束窗口，沿旧反馈入口路由公开结果；不自行建模、写入、
  批改 Judge 或读取隐藏答案修模。不可用／过期反馈如实记未执行／失效。
- `ontology-modeling/SKILL.md` 及其 `references/prompts.md`、`platform-flow.md`：
  同步应用证据与业务读取的用途，消除先完整资源读回才启动早期反馈的重复表述。
- `skills/modeling-dev-loop/references/team-runbook.md`：明确既有公开反馈入口的窗口
  顺序、成功回执信任和安全恢复边界；不引入新的宿主脚本或强制每切片 CQ。
- 当前 `r4-0-009-multiview-semantic-acceptance.yaml`：在 objective／说明中解释
  `authorized-scope-readback-complete` 指必要业务读取及整轮实际语义检查的覆盖，继续
  保留该既有标签；不解释成每个已应用计划的逐项重验，也不把应用回执当成该标签完成。
- R4.0-024 合同及独立 Consumer／Judge 输入不变。R4.3-001—007 旧设计的历史结果保留，
  标注本设计对正常成功后资源核验边界的增量覆盖，不能据旧 PASS 宣称本期已交付。

## 7. 实施触点及影响

| 文件／责任 | 拟议最小改动 | 当前边界 |
| --- | --- | --- |
| `modeling_team/runner.py` | `_handle_execute_approved_plans` 成功及 already_applied 返回状态／后续动作 | 不改 staged submission、Attempt proof、原子性、版本确认或恢复算法 |
| `modeling_team/capability_mcp.py` | 对应工具 description | 输入 schema、工具名及 capability handler 不变 |
| `modeling_team/delivery.py` | `_read_artifact` 对绑定 run 的 early-feedback 目录及保留响应读取对齐 | 原文件范围、大小限制及 content digest 返回保留，不新增 Host 工具／权限框架 |
| `modeling_team/agent-packages/{protocol,coordinator,modeling,delivery}/instructions.md` | 上述具体用途、反馈窗口及完成语义 | 只调整活跃要求，不扩大全仓库／隐藏资料权限 |
| Modeling 方法、Host runbook、当前 Task | 第 6 节对应段落 | 无新增切片、小链、阶段字段或运行机制 |
| `modeling_team/tests/test_v43_production_refs.py`、相关 transport／反馈／model-check 测试 | 第 8 节正常结果及反例；保留真实关联读取测试 | 不把 prompt 字符串通过当作真实 Agent 行为改善 |

本轮只写文档，尚未实施这些触点。采用当前符号及调用点检查，未使用 GitNexus 图分析，
不声称图覆盖；设计／文档提交不要求图索引重建。后续代码实施按实际影响和仓库要求检查。
不改 `backend/`、`frontend/`、平台 schema、Consumer/Judge 评分、checkpoint 存储或
恢复框架。若实施发现与本设计不同的真实合同缺口，披露证据并修订最窄部分，不顺带扩展。

## 8. 验证范围与独立审阅

下表是后续实施验证意图，本轮不执行产品测试、服务重启或真实运行。

| 编号／需求 | 有效验证与反例 |
| --- | --- |
| V1／A1—A3 | 复用 native broker fixture 执行依赖计划，验证精确 projection、当前版本及原审批；正常成功／already_applied 为 not_evaluated，可继续执行，没有强制资源扫描；dry-run 仍 not_applied |
| V2／A3、A7 | 保留缺终态证明、引用失败、版本确认失败及 apply 中途失败反例；保持第一错误、完成项和原恢复身份；重试不重放已应用计划 |
| V3／A4—A6 | 复用 Delivery／公开反馈 fixture 检查已有消息暂停新提交、等在途结束、实际反馈结束后释放；partial／unavailable／superseded 同样可继续；结果丢失仍绑定原 operation，未知写入不被释放；当前 operation 的实际反馈正文／响应可读，旧／错 digest、跨运行路径或过界输入不当作当前证据 |
| V4／A3、A8 | 将原“执行后必须读回”测试拆分为正常执行合同与独立显式最终关联检查；保留 ScopedSparql 实际完整分页、共享目标、游离处置及修复复查证据；不删除扫描能力或将 pending 改名后继续强制逐批扫描 |
| V5／A6、A8—A9 | 活跃角色／方法合同检查应用、质量、未知分账及真实依赖判断；保留最终交接只读、完整分母、独立性、公开／隐藏隔离和旧 formal 合同回归 |
| V6／真实效果 | 新获准运行中核对每次资源读取的业务用途、首链反馈及最终覆盖；对照调用／输入开销、有效语义时间和同范围质量，不能由 fixture 或文档 PASS 推导提速 |

Team 代码实施后从 `backend/` 运行 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest
../modeling_team/tests`，并完成要求的独立功能验收。仅 Team／提示变更不重启平台；实际
触及 backend/frontend 时按仓库规则补全测试、重启和受影响健康验证，不提前授予这类改动。
真实建模及性能验证另依原授权，保持现有暂停及额度，不以设计审阅触发运行。

独立设计审阅核对需求、当前代码及上述取舍，报告可阻断实施的 Critical／High 和未决
关键假设。发现阻塞后保留原轮记录，修订并复审；文档／链接检查、设计 PASS、工程及
独立业务验收分别记录。本轮不要求额外设计测试 Agent、mock harness 或独立语义判定。
