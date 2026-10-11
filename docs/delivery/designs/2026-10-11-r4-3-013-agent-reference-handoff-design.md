# R4.3-013 Agent 文件／目录引用交接设计

## 1. 范围、基线与状态

- 权威范围：[R4.3-013](../../requirements/requirements-v4.3.md#r43-013-agent-自主选择文件或目录引用交接)。
  2026-10-11 设计阶段授权需求细化、设计及独立测试；随后用户授权按本设计实现并测试。
  不包含外部模型调用、恢复建模或消耗额度。
- 设计时静态代码基线：`main@0b73001`，开始时工作树干净。下文保留设计阶段的增量与基线描述；
  当前已实现工具合同见[引用交接工具](../../../modeling_team/references/handoff-materials.md)。
  独立设计审阅与设计测试结果记录在[共享测试记录](../test-plans/2026-10-11-r4-3-013-agent-reference-handoff-test-plan.md)。
- 复用 R4.3-003 的确定性引用执行、R4.3-006 的冻结原文读取与 R4.3-007 的响应去重。
  不新增平台 HTTP 接口、数据库、文件服务、通信边、通用审批或运行编排。
- 本文覆盖既有 production、Delivery／Host、CQ、Consumer／Examiner、Judge／Acceptance
  和已授权修复交接；网页用户上传不在本条 Agent 交接范围。
- 当前状态：独立 `plan_reviewer` 审阅 PASS，0 Critical／High，无关键待确认假设；
  独立 `r4313_design_test` Round 1 的 T01—T08 设计测试 PASS，文档合同检查通过。
  工具名 Low 问题修正、只读输出及 legacy 报告预算隔离澄清均已复核，初稿证据保留在共享记录。
  2026-10-12 工程实现与独立功能 Round 3 PASS，详见[交付记录](../records/2026-10-11-r4-3-013-delivery-record.md)。
  真实交接效果和独立语义质量未验证。

例：Modeling 已保存一份大候选和三份切片说明，只发送“请审核此候选及说明”与引用。
Runner 保存本次文件集合的不可变副本，Coordinator 在自己的通道列目录、读所需原文。
原文件随后修改不会改变这次消息；正式候选仍以被引用的完整 JSON 通过原校验。
正文交接仍可使用相同入口，由 Agent 决定。

## 2. 设计时能力与需补齐的增量

| 实际入口 | 已有能力／限制 | 必要增量 |
| --- | --- | --- |
| [transport_mcp.py](../../../modeling_team/transport_mcp.py) 的 `Delivery`、`TeamTransportBroker.send`、`mcp_response` | Profile 限定边、稳定 delivery_id、反向回复槽；send schema 只接收 text，结果也返回完整正文 | 增加可选引用，发布时校验，返回定位元数据；正文路径兼容 |
| [runner.py](../../../modeling_team/runner.py) 的消息 drain、`_observe_formal_candidate_delivery`、stage handoff 登记 | 正式候选、Protocol receipt 和 handoff 解析 delivery.text，消费原 delivery 身份 | 先解析完整正文引用再进入这些相同入口；原身份和回复槽不能断开 |
| [runtimes/base.py](../../../modeling_team/runtimes/base.py) 的 `RuntimeDelivery`、[runtimes/codex.py](../../../modeling_team/runtimes/codex.py) | 接收消息目前只有 text；bubblewrap 只绑定本角色工作区及明确资料，部分角色沙箱只读 | 分开运行时展示和正式正文；增加角色私有输出目录与受限引用读工具 |
| Codex `_staged_decision_binds`、`_competency_question_binds`、`namespace_command` | 已有候选／计划共享只覆盖指定角色；CQ 私有审核不挂给生产 | 用现有源根映射及权限判断注册本次材料，不挂载整个 run 或所有角色目录 |
| [coordinator instructions](../../../modeling_team/agent-packages/coordinator/instructions.md) | 拓扑文件由 Coordinator 独占；当前要求他人用消息正文交建议 | 可接收引用建议，但地图所有权及拓扑决策不转移；只发布 Protocol 所需决定内容 |
| [delivery.py](../../../modeling_team/delivery.py) 的 `DeliverySession.call_tool`；[runtimes/delivery.py](../../../modeling_team/runtimes/delivery.py) | Delivery 仅有动态 Host 工具，无 shell／通用文件读取；持有 allowed_sources 和 run_ids | 通过原动态工具发布／列举／读取受限引用，不能要求 Delivery 调用原生文件或开启 shell |
| Runner `_publish_cq_question_draft`；[CQ Profile](../../../modeling_team/profiles/r3-0-011-competency-question.yaml) | CQ 无 Team 通信边；draft/review 经 Runner 私有 capability，公开投影单独发布 | 在原 capability／Host 输入加内容引用分支，保留公开／私有处理与冻结规则 |
| [acceptance_runtime.py](../../../modeling_team/acceptance_runtime.py) 的 `V3BatchReportContract.read_frozen_evidence`、`ReportSinkServer`；[report_sink_mcp.py](../../../modeling_team/report_sink_mcp.py) | Judge 已可按引用读冻结业务材料；Consumer／Judge report sink 是角色／attempt 绑定的正式提交 | 复用冻结读取；补充获准目录和报告引用解析，继续走原报告校验、实际读取回执及提交 |
| Delivery `prepare_repair_task` | 仅允许已授权 public repair references 和 owned_paths | 修复材料可用目录引用，但只能解析现有获准公开集合，不复制隐藏报告 |

当前共享目录、专用 refs 和部分读取工具不是全角色交接完成证明。实施时需核对 native
动态工具、MCP、角色 packet、工具清单预检和实际加载提示；只改某份提示不能交付本需求。

## 3. 决策主表

既有用户确认不重新评分。技术选择均在本次设计授权内采用，主观把握明确超过 85%，
依据为已核对的通道及隔离限制；不表示用户逐项批准或实测概率。没有未决业务／范围选择。

| 编号 | 采用方案及实际取舍 | 依据与状态 |
| --- | --- | --- |
| D1 | 正文、文件、目录或简短说明加引用均可用；大材料提示推荐引用，无强制大小门槛 | 沿用已确认原则 |
| D2 | 在原通道上增加可选 `material_refs`／`body_ref` 与受限发布、列举、读取；不另建文件服务 | 按授权采用，明确超过阈值；已有 Broker／Host／sink 可承接 |
| D3 | 发布时保存限定文件集合的不可变副本和工具生成 manifest；复用已有不可变材料时引用原绑定 | 按授权采用，明确超过阈值；直接引用可变路径无法保证消息内容身份 |
| D4 | 权限由原通道、源授权和接收角色共同决定；CQ 私有／Judge 隐藏／生产资料保持隔离 | 沿用既有边界；具体登记及过滤方式按授权采用，明确超过阈值 |
| D5 | 正式正文引用解码后进入同一校验、批准、回执链；辅助目录不自动成为正文或写入计划 | 按授权采用，明确超过阈值；现有解析依赖 delivery.text／原报告结构 |
| D6 | 原文与目录均可分页读取，结果明确未读完和继续入口；发送／读取／业务完成分别表达 | 沿用完整送达要求；分页合同按授权采用，明确超过阈值 |
| D7 | 为无既有文件写入口的角色提供受限私有输出工具；原沙箱与 native 工具边界保持 | 按授权采用，明确超过阈值；避免仅为交接扩大只读角色写权，Delivery 沿原动态工具接入 |
| D8 | 一份通道覆盖清单，复用现有错误及保留生命周期；独立设计检查先行，工程与真实验收分层 | 按授权采用，明确超过阈值；不将文件交付、计数下降当作语义 PASS |

相比只约定“在 text 里写路径”，本方案补齐实际可读及正式内容处理。相比开放共享 run 根目录，
限定副本和工具读取能保持当前隔离。副本有局部存储成本，用既有 immutable artifact 时不重复复制；
不为理论存储规模新增全局缓存、引用计数或回收服务。

## 4. 引用、发布和读取合同

### 4.1 主体、源与目的通道

Host 根据当前 Task／Profile／role_sources、Delivery allowed_sources、acceptance packet／attempt
及已授权 repair 输入生成源根映射和通道允许集合。Agent 提交在自己环境可见的路径，Host 只通过
该角色映射解析；不接受任意宿主绝对路径、URL 或另一个 run 的路径。

发送方可读不代表接收方获准。材料只能来自：双方当前获准来源，或该通道已允许交接的
角色自产物。不得由 sender 自报 visibility／recipient 字段扩大权限。发送方可以选原通道中的
一个接收方，最终读取主体由既有 socket／token／session 身份确定，不能由 read 参数伪造。

CQ private／reviews、hidden 题与答案、Judge 私有判据／报告、密钥、其他角色 home 和整个
workspace 不作为生产来源根。新私有输出目录不会把这些源根变成公开。CQ／Judge 自产物仍受
其 Host-only 路由约束；给生产的公开 projection 或诊断仍经原正式发布／公开修复交接。
工具只实施可观察的来源和路由限制，不声称能自动辨别任意正文里的业务语义或隐藏答案。

现有 role_sources／运行配置若无法确定某条材料的接收权限，拒绝该材料并返回缺少的授权绑定，
让 Host 在原授权范围内补充登记；不能靠新增 Profile 边或开放全部源目录修复。

### 4.2 发布对象

复用当前保留 artifact 方式，拟在所属 run 的 `handoff-materials/` 下保存 publisher 私有源及
Host-only 发布副本；Delivery 直属材料保存在所属 session 同名目录。验收材料归其原 attempt。
这些是本地 gitignored 产物，不成为平台模型资源或新的完成状态。

`publish_handoff_material`（拟议工具）的输入包括目的原通道、源路径和可选目录成员集合。
单文件直接选择；目录可以省略 members 表示“该目录本次全部文件”，也可显式选子集。
发布前完整列举实际选择集合，保留相对路径；目录大时返回清单分页，Agent 不需抄写文件名。
不能只保存当前显示的一页。根目录混入不允许的成员时整个发布返回定位错误，不静默过滤后
宣称整目录交付。仅支持当前材料所需的普通 UTF-8 文本文件，拒绝二进制／socket／设备文件。
不跟随 symlink，拒绝越界、`..` 和经链接逃出来源根；文件名不是权限或正文的证明。

Host 读取并保存文件字节、SHA-256、长度与相对名称，然后生成 manifest。复制中发现源缺失、
变化或读取失败则不交付部分包。普通草稿的副本是该次发布内容，不承诺跨文件业务原子性；
正式候选、计划、冻结材料按原内容版本／摘要校验，副本必须与该绑定一致，不能由新包装替换。
原不可变材料可登记现有 artifact，而不重复复制；查找时仍校验原身份和可用性。

发布结果包含以下拟议结构，ID 为 Host 生成；示例只是合同示意：

```json
{
  "material_id": "material-opaque-id",
  "kind": "directory",
  "manifest_digest": "<sha256>",
  "file_count": 4,
  "total_bytes": 42000,
  "binding": {"run_id": "run-id", "publisher_id": "modeling", "recipient_id": "coordinator"},
  "list_complete": false,
  "next_cursor": "<opaque>",
  "entries": [{"path": "candidate.json", "digest": "<sha256>", "bytes": 30000}]
}
```

真实 binding 根据通道使用原 run／session／attempt 及原授权身份，不要求不存在的统一全局 ID。
manifest 包含完整文件集合、每文件内容身份、源定位和已有正式版本绑定；定位由工具记录，
Agent 不填摘要。通道可见的 manifest 只列该接收方获准的集合，不暴露被拒源的目录清单。

### 4.3 列举和读取

`list_handoff_material(material_id, cursor?)` 返回稳定按相对路径排序的 entries、manifest_digest、
list_complete 和 next_cursor。cursor 绑定主体、所属运行和 manifest；不存在材料或越权不泄露名称。

`read_handoff_material(material_id, path?, offset?, max_bytes?)` 读取已发布集合中的一份文件；
单文件可省 path，目录须选择实际 entry。返回 content、content_digest、实际 offset／next_offset、
read_complete 和截断说明；offset 是字节位置，文本页切在 UTF-8 边界，避免丢字／重复字。
无论默认或显式分页大小，工具不得静默截断原文。输出大小受现有工具／native 体积约束，
但源材料大不要求发送方改用正文或拆写。正式校验在 Host 端读完整文件，不依赖 Agent 展示页。

每次调用检查原主体和当前授权。复用 R4.3-006 的同身份／同冻结绑定读取回执，不用新通用
读取计数门；辅助材料允许按需读取，不能强制读每个文件才能回复。Judge 所需资料已读的
证明仍由原合同判断，不以通用 read_complete 替代。

发出引用、消息已送达、文件已读全、正式内容获批／执行以及业务完成分别沿原回执表达。
读了一份文件不等于目录所有文件已读，列举完整也不等于正文已读。

### 4.4 留存及恢复

已交付副本和 manifest 沿现有 run／session／attempt 证据目录保留。源文件修改、删除不改变
副本；重新发布是新 material_id，旧消息不自动跟随 latest。内容损坏给出 digest mismatch，
不能静默重建并覆盖旧消息。撤权立即停止新读取，既有不可变证据不删除。
checkpoint／resume 若包含待消费引用，按原获准产物打包规则纳入 manifest 与副本，恢复时
重新核对主体、源授权和正式绑定；不会把验收私有材料塞进生产恢复包。缺失引用可重新发布
并通过原消息／重试交接修正，保留旧失败。没有额外 TTL、后台回收、跨机器文件分发或
“通用恢复状态”；R4.3-014 的剩余工作核对仍单独负责。

## 5. 原通道集成与正式内容等价

### 5.1 Team 普通消息与正式交接

`send_team_message` 保留 recipient_id、expects_reply、reply_to_delivery_id，拟增加
material_refs（辅助材料列表）与 body_ref（一个文件／目录中的一个成员，作为正式正文）。
无引用时 text 原合同不变；只有辅助 refs 时 text 提供用途和接收方任务。body_ref 模式可附
简短 text 作展示说明，缺省说明由工具给出定位；**该说明不与文件拼接成正式 JSON**。

发送的顺序为：原通信边检查 → 发布／引用及接收权限检查 → 完整正文解码与原 pre-send
校验 → 记录 Delivery 和原回复槽 → Runner 消费／Runtime 投递。引用失败不能消耗回复槽、
建立假完成记录或令 run 永久失败。既有报告／业务校验拒绝沿原反馈处理，不绕过其权限门。

Host 归一化后的 `Delivery.text` 为原完整正文，供 `_observe_formal_candidate_delivery`、
stage handoff、candidate revision／receipt 等原消费者处理。保持原 delivery_id、原候选
版本和正文语义摘要，material_id／manifest_digest 只是传递身份，不能代替业务 digest。
`RuntimeDelivery` 增加可选引用及展示说明，接收 Agent 初始只见说明和定位，通过读取工具取原文。
不能把完整大正文又塞入初始 runtime 消息或 send 返回值；无引用调用的返回保持兼容。
正式消费者不依赖接收 Agent 已读完，接收 Agent 作业务审阅则必须有自己实际阅读依据。

辅助目录不自动触发候选注册、审批、CQ 冻结或 apply。目录中有多个 JSON 时正式 body_ref
必须明确一个成员；不按文件名猜类型、不自动合并。原 typed dispatch／draft-from-delivery
继续消费原 delivery 身份和完整已校验对象，不要求 Agent 改回逐字粘贴。

`report_task_result` 的终态 status 与原 guards 不变，增加可选 summary_ref；Host 解析为
原 summary 后再调用 guard/report。长报告作为辅助引用不自动证明 completed。固定 coordination
消息如需辅助材料也可附 refs，但 message_kind、generation 及终态语义不变。

### 5.2 全部获准通道覆盖清单

| 通道 | 发布／输入和读取接入 | 正式处理及隔离 |
| --- | --- | --- |
| Modeling／Protocol／Coordinator 的 Profile 直接边 | 原 Team 工具可附 file／directory refs；角色私有发布／list／read 工具 | body_ref 经同一候选、revision、receipt、hand-off 校验；不新增边 |
| 生产角色 → Runner 的 result／coordination | 原 terminal summary／phase 工具可附 refs | 原终态依赖／phase guard，回执不等于语义 PASS |
| Delivery ↔ Host／Runner ↔ Coordinator | 原 `submit_instruction`／`answer_question`／`consult_team` 等获准操作加可选引用适配；观察公开产物可列举／读 | 保留授权引用及 source attribution，Delivery 不加入 Team roster／Broker 边 |
| CQ ↔ Runner／Host | 原 draft capability、审核答复与后续输入支持 body_ref／辅助目录；只在 CQ 原 capability 上提供读／发布 | 草稿完整对象仍进 `validate_draft_document`；private notes 不进公开投影／生产消息 |
| Host → Consumer／Examiner | 原 role packet／proxy 只登记当前问题获准输入和受治理响应引用；受限 list/read | 不给 Platform Examiner 原始 source；不得用静态文件替代首次受治理查询、授权及完整页证明 |
| Consumer／Examiner → Host → Judge | 原 report sink 支持 report_ref，Host 校验报告并组织原 Judge packet；响应 refs 保留 tool/request/page/response 身份 | 完整 question 集和证据一致；Judge 只读冻结资料／保留响应，不新增在线查询 |
| Host → Judge／Acceptance → Host 或获准 Coordinator | 沿 `read_frozen_evidence` 读取业务原文；目录列举覆盖冻结清单；报告引用复用 sink/原 verdict 路由 | PASS 仍依赖原实际读取及独立裁决；给生产的诊断走原公开修复投影，不直接放行隐藏包 |
| Delivery／Host ↔ 已授权修复角色 | 仅原 repair task 的 public references／owned_paths 和安全结果；追加 list/read／报告引用 | 不新增生产写权、不授予旧隐藏答案、不自动恢复 run |

清单覆盖当前通道，不承诺表中每个角色彼此互通。disabled role 不注册边，CQ 无 Team 边的
现状保持。Legacy v1 Examiner／Acceptance 和 native/MCP 等实际仍可选路径也须支持引用适配，
不能只在 v3 batch 实现后宣称全覆盖；原 packet schema 和必需 evidence 字段保持。

Delivery／Host 操作具体复用 [host_ops.py](../../../modeling_team/host_ops.py) 和
[host_ops_mcp.py](../../../modeling_team/host_ops_mcp.py) 的 `consult_team` 等已发布入口。

报告引用需同时改 child-local `report_sink_mcp.py` 的 schema／参数解码和 Host
`ReportSinkServer._serve`，顺序为：原 token／角色／attempt 鉴别 → 完整解析 report_ref
及材料绑定 → 原报告字段／evidence 校验 → 原报告提交和回执。引用读取、缺成员、摘要或
绑定错误在进入原报告验证／重试计数前返回，不增加 legacy `_rejections`，也不触发
`report-attempts-exceeded`。旧单报告原本对真正报告错误的次数规则不由本条扩展或取消；
v3 batch 保持原可修正机制。超过三次引用读取失败后仍应能用有效正文或引用提交原报告，
不能只在工具外层返回友好错误而让 sink 已耗尽机会。已成功报告仍按原回执查结果，不重复提交。

### 5.3 角色输出与实际加载

Runner／Host 为启用角色准备私有 `handoff-output/<agent_id>/`。已有文件写入口的角色
直接发布其获准候选／计划／私有文件，不必重写一遍；其私有 agent.work 本来就由 Host
定位，不将该工作区向接收方开放。没有既有写入口的角色通过 scoped
`write_handoff_output(relative_path, content)` 在自己的输出目录生成一次新内容，随后
可反复按引用交接。该工具不接受源根外路径，不覆盖正式候选／冻结资料；输出目录写入
不表示内容已正式发布或获批，也不授予接收方读权。

原角色 package／thread sandbox 与源文件写权限保持。Team 角色在其原 MCP／native
工具通道接入；CQ 经原 Runner capability；Consumer／Judge 经原 report capability。
Delivery 没有 shell，仍仅使用 dynamicTools 接入同一受限工具，优先复用已有 Host 产物。
不为生成文件开启 native builtins、提升 workspace-write 或增加通用平台权限。

相关实际加载提示推荐大候选／计划／报告或多文件材料用引用，给用途、入口和接收任务；
简短沟通用正文；读取失败反馈位置。同步 coordinator 的“必须抄消息正文”、Protocol 的完整
候选接收、CQ draft 输入、Consumer／Judge report sink 说明、Delivery 动态清单及 skills。
原源忠实、工具读取、正式审阅、unknown 和独立验收要求不被提示建议取代。

## 6. 可恢复错误

以下为拟议错误类别，按现有 response／issue 通道返回，定位只显示该主体获准的信息。

| 错误 | 反馈与修正 | 保持的不变量 |
| --- | --- | --- |
| `material_source_unavailable`／`material_source_changed` | 指出自己选择的缺失／变化文件，重新选择或发布；未送达包不算完成 | 不交付部分包、不覆盖旧副本 |
| `material_forbidden` | 返回授权／通道不匹配，不枚举受保护目录 | 不扩大源或通信边 |
| `material_member_required`／`material_member_missing` | 返回本次获准清单入口，选择实际正文成员 | 不猜正式 JSON、不消费回复槽 |
| `material_digest_mismatch`／`material_binding_changed` | 保留错误引用，重新核对原版本；原冻结／批准变更走其既有路径 | 不用重新包装替换正式身份 |
| `material_cursor_invalid`／`material_read_incomplete` | 给当前获准的续读／重新列举入口及未读部分 | 不把截断当全文，不丢失读状态 |
| `material_path_invalid`／`material_media_unsupported` | 返回自己提交路径／类型的具体错误；可换正常文件或用正文 | 不读取宿主任意路径，不禁用正常通信 |

只阻止当前不安全／不完整材料的交付或使用。普通引用错误不是 terminal blocked 的自动
理由，也不自动 kill run。无副作用失败可修正后重试；发送结果未知时查原 delivery／request
回执再决定，不新造重复正式提交；成功发布但未发送的包沿当前运行留存，不建清理调度。

## 7. 实施交接与验收

按以下依赖完成一个范围内增量，不能把独立功能 PASS 或真实效果前置为设计 PASS：

1. 增加小型 Host 引用辅助模块（拟 `modeling_team/handoff_materials.py`），复用既有
   摘要、safe path、私有写入、artifact 和错误方式；完成源映射、限定发布及分页读取。
2. 接入 Broker／Runner／RuntimeDelivery 和正式 content 归一化；同步 native/MCP 工具
   schema、tools/list 预检、summary／coordination 与现有 typed delivery 消费。
3. 接入 Delivery 动态工具、CQ capability／Host 操作、Consumer／Judge packet 与 report
   sink、legacy 可选入口和修复公开材料；以第 5.2 节覆盖清单核对，无空行宣称覆盖。
4. 更新实际角色提示与相关 Team skills、必要 checkpoint 产物选择及工具接口文档。
   改公开工具／跨模块时做 GitNexus impact 或当前调用点核查；本轮文档无 symbol 改动。
5. 开发和独立测试覆盖 [A1—A8](../../requirements/requirements-v4.3.md#r43-013-agent-自主选择文件或目录引用交接)
   及[共享用例](../test-plans/2026-10-11-r4-3-013-agent-reference-handoff-test-plan.md)，随后按另行
   获准运行验证真实角色是否选用、读原文、减少搬运以及质量边界。

实施时需验证受影响 Team 回归、原 native／MCP／packet 合同和 changed skill validators。
如修改 backend／frontend 再执行其规定的全套检查与重启；仅 Team 文件不额外重启应用。
保留第一次失败和修正证据。运行授权仍按现有暂停、额度和独立验收合同处理。

设计阶段完成门是需求／设计一致、原通道可定位、反例有明确处理、文档检查及独立设计审阅／
设计测试通过。真实接收环境中的文件可读、正式处理等价、返工减少和业务质量仍属实施后
验收，不从本文方案或审阅结果推导。

## 8. 2026-10-12 工程交付结果

基于 `954f1601e3a79787adfaf929b16bd0edc548b2c3` 完成本设计增量，实际引用工具与参数见
[工具合同](../../../modeling_team/references/handoff-materials.md)。正式摘要引用字段为 `summary_ref`，
消息正文为 `body_ref`，报告为 `report_ref`；各自解析后进入原合同。checkpoint 仍使用原 artifacts，
未另建材料包字段、服务、审批或恢复编排。角色提示与 native／MCP／legacy 清单同步。

开发完整 Team suite 2660 passed／11 skipped；独立功能 Round 2 发现协调通道 decoder 与
Runner 引用／证据缺口，局部修复并增加真实通道回归，Round 3 复测 81 passed，最终工程功能 PASS。
历史、冻结输入和逐项验收见[共享计划](../test-plans/2026-10-11-r4-3-013-agent-reference-handoff-test-plan.md)，
交付与检查见[记录](../records/2026-10-11-r4-3-013-delivery-record.md)。
真实 Agent 行为改善及独立语义质量未验证，未启动模型调用或消耗额度。
