# 引用式材料交接工具合同（R4.3-013）

工具由 Host 保管快照；角色只能通过当前已授权的工具入口读取或发布。Team transport、Delivery
Host 工具、CQ 原有 capability 和隔离验收 report sink 均提供以下四个工具。它们不增加角色、通信
边或文件读取权限。接收者必须使用当前入口公布的引用，跨 run 或跨子会话的材料由 Host 重新绑定。

| 工具 | 参数 | 返回与使用 |
| --- | --- | --- |
| `write_handoff_output` | `relative_path`, `content` | 在角色私有交接目录保存 UTF-8 文本，返回可发布路径；不提供 shell 或任意文件写入。 |
| `publish_handoff_material` | `recipient_id`, `source_path`, 可选 `members` | 对获准文本文件或目录发布固定快照；目录默认包含全部获准成员，`members` 指定子集。返回 `material_id`、条目和继续游标。 |
| `list_handoff_material` | `material_id`, 可选 `cursor`, `max_entries`（1–100） | 返回稳定排序的 `entries`、`next_cursor`、`list_complete`；继续至完整，不把第一页当作全部成员。 |
| `read_handoff_material` | `material_id`, 可选 `path`, `offset`, `max_bytes`（1–16384） | 返回 `content`、字节偏移 `next_offset`、`read_complete`、`truncated`；目录必须指定成员，按继续偏移读取至完整。 |

引用格式为 `{"material_id":"…"}`；目录成员引用增加 `"path":"relative/file.txt"`。读取按
UTF-8 字节边界分页，不截断字符；页上限小于单个字符时仍返回完整字符。源文件修改或删除不改变已发布内容；摘要、身份或授权变化会返回
`material_*` 类型错误。路径逃逸、符号链接、非 UTF-8 文件、未授权来源或接收者拒绝发布，不产生
可用半成品。修正引用或参数后可在原通道重试。

Team `send_team_message`、`send_coordination` 可携带 `body_ref` 和 `material_refs`；
`report_task_result` 的正式摘要引用字段为 `summary_ref`，辅助材料仍用 `material_refs`。
`body_ref` 的完整正文先恢复，再进入原有合同校验；`text`／`summary` 可只说明目的、入口与接收任务。
`material_refs` 是辅助材料，不能替代必需正文。无引用时原内联调用继续有效。Host 的指令、业务答复、
CQ 访谈和评审遵循相同规则，仍使用原入口、身份和状态推进。

验收 `submit_examiner_report` 可选择原 `report` 或 `report_ref`。引用正文必须是符合原合同的完整
JSON 报告；材料错误不消耗报告格式纠错次数。冻结材料读取仍产生原冻结证据读回回执，受治理实时
读取仍通过原代理；发布、列目录、分页元数据和显示提示均不构成已完整阅读或语义验收通过。

引用提示应说明目的、材料入口和接收任务。长材料优先引用，短澄清可内联。使用获准来源或私有
交接输出；CQ 私有材料、Coordinator 私有全景图和独立验收隐藏证据不得借引用传给生产角色。

## DSH运行期接线（R4.3-035）

DSH生产Coordinator通过`write_handoff_output`写以下既有路径时，Host沿同一工具调用自动
保存不可变handoff原件、将原字节接入Runner目标，并返回`runner_receipt`：
`scenario-map/scenario-map.json`、`scenario-map/topology-decision.json`、
`scenario-map/protection-iri-suggestions.json`。回执含run、actor、源、目标、摘要、material_ref
与received事实。它不表示地图/拓扑准入或语义通过。其他私有输出继续原行为。
失败按原内容重试；同版已接收不重复覆盖，目标或原件发生变化须先核对准确错误。

Host审核后Runner发布`cq-public-input`消息：包含run_id、递增投影文件version、
projection_digest和固定material_ref。生产通过原list/read_handoff_material领取原文，
按分页元数据续读。只有真实freeze后才附batch_id、snapshot_digest；私有CQ快照和隐藏材料
不进入生产。旧版迟到仍保留旧身份，应按version识别，不把它当最新事实。

`evidence/dsh-handoff.jsonl`记录原件接收和公开输入交接；`dsh-dispatch.jsonl`及原生wire
保留消息入队、领取、活动结束与取消/未知状态。queued不是已读，claimed不是语义完成。
明确失败/取消允许原身份重试；unknown先核对原dispatch及迟到响应，不能重复发送。
材料/派发失败由后续Runner drain重试可安全的未送事项，不要求人工复制或新开建模run。
