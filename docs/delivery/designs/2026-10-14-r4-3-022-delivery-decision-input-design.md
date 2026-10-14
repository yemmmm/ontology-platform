# R4.3-022 Delivery 决策输入与按需原文读取设计

## 1. 范围、授权与例子

权威范围：[R4.3-022](../../requirements/requirements-v4.3.md#r4-3-022)，承接
R4.3-005／013／015、R4.0-021／023。2026-10-14 用户要求“请先完成022设计并通过审阅”。
本轮仅需求细化、设计及独立只读审阅，不实施、不启动服务、不调用外部模型或建模。
静态代码基线 `e4efc23`；开始时仅有无关未跟踪目录 `docs/presentations/`、`slide-deck/`，不纳入。
设计状态：独立审阅 Round 1 PASS，0 Critical／High，无未决关键假设；工程与真实效果
A1—A6 均未执行。详见[审阅记录](../records/2026-10-14-r4-3-022-design-review-record.md)。

例子：同一 run 已完成 100 次 Host 请求，当前还有一次 CQ 审核请求未决，公开反馈刚产出报告。
Delivery 默认应看到当前审核绑定、未决请求、新回执、报告绑定及准确原件入口；不再次收到
100 次历史提交正文与日志尾部。审核时读取本次问题和相关业务依据；组织公开反馈时读完
本次选定问题的实际答案、读取证据和完整反馈。两个原件的路径或 PASS 字段不能代替这些读取。

采用确定性投影及现有读取工具的有界扩展。拒绝以第二个 LLM 生成摘要：会新增调用、可能
改变事实，且不能解决版本及完整性。也不只删除日志尾部：累计账本和历史 operation 仍会增长。
不建设新状态服务、事件总线、观察角色、通用查询语言、业务读模型或自动恢复框架。

## 2. 当前实现与最小增量

| 实际入口 | 已有行为 | 本条增量 |
| --- | --- | --- |
| `modeling_team/delivery.py::DeliverySession.observe` | 汇集 status、pending、增量 events、累计 host-requests 全文、operation、verification | 保留完整原始观察；从相同观察确定性组织决策输入及引用 |
| `record_observation`、`_decision_observation`、`_decision_events` | observation.json 原子替换；过滤噪声计算唤醒指纹；事件按 source/byte_offset 去重 | 指纹与输入分别处理；实际变化正文可读取，不只交付事件链哈希；仅按已知元数据路径去噪 |
| `_model_observation` | 主要去掉 app-server 通知，其余完整传入 | 改为本设计当前状态、未决集合、变化及原件定位 |
| `_run_delivery` | resume 初始输入、busy steer、idle send 共用投影；pending_observation 可被新观察覆盖 | 三条路径共用新输入；待投递变化不被后页覆盖，沿原 thread/turn 投递 |
| `_read_artifact`、本地 `read_delivery_artifact` schema | 授权路径全文 UTF-8 读取，2MB 上限，返回 SHA-256 | 保留 path-only 旧调用；增加字节区间／精确 JSON 字段读取及版本核验 |
| `host_ops.py::get_run_events` | 每源 byte_offset 游标、最多有界事件页；大行 placeholder、近似时间排序 | 原分页及顺序不变；用源字节位置定位原事件，不将 line_no 当全文件行号 |
| `host_ops.py::get_request_result` | receipt 优先；与 ledger 的 digest 冲突报错；submitted／unknown 分开 | 原结果判据复用，不自建 accepted/consumed 判断 |
| `delivery_ops.py::get_evaluation_status/get_repair_status` | request/report 绑定、资格错误、control/consult、尾日志与原件路径 | 原 Host 合同不改；在 Delivery 输入层投影，按绑定原件补读 |
| `handoff_materials.py::HandoffMaterials.read` | 不可变包、16KiB 字节分页及 digest／read_complete | 文件包继续用原工具，不转换成任意 Host 路径 |
| Delivery `instructions.md`、`skills/delivery/SKILL.md` | 组织 CQ、首链反馈、授权／收尾及完整证据读取职责 | 指导先读必要状态和定位，再补本次需要的原文；不减少职责或扩大权限 |

`get_run_status` 等 Host／MCP 的公共签名和原始输出不改。`observe` 的内部取证与模型显式
调用工具分开：内部继续取得完整工具回执，不能因使用新的模型投影把原始 observation
替换为精简版。模型显式请求现有详细状态仍可用；默认观察不重复注入该全文。
本轮为文档工作；后续开发按实际差异进行 call-site／GitNexus 影响核对，不宣称已完成图覆盖。

## 3. 决策输入合同

### 3.1 当前状态与变化

保持外层 `kind=host_observation`（接续仍为 `delivery_resume`），`data` 采用局部
`schema_version=delivery-decision-input/v1`。这只是 Delivery 原生会话输入格式，不是新平台 API。

| 部分 | 默认内容与完整性规则 |
| --- | --- |
| `session` | 当前 session、授权 reference／期限／allowed_operations、实际用户控制／flow_confirmation、activity／work_result；不存在的授权余额不推算 |
| `runs` | run 身份／task_id、阶段、recorded state／lifecycle／work_state／write_phase、真实存活判据、semantic_progress 中的成果／版本绑定、first_blocker、原有 limitations |
| `pending` | 所有当前必要待办、business_question／issue／review 身份、状态、来源和 available_actions 所需绑定；大正文按精确引用补读；不只保留 counts |
| `requests` | 全部未决／unknown／冲突项，及相对上一已投递输入新增或变化的真实结果；保留 run/request/action、digest、outcome、错误及原 ledger/receipt 定位 |
| `operations`、`repair_verifications` | 活跃或未收口项的真实状态、当前角色、用户控制回执、未决 consult、报告／修复／核验资格和版本绑定；本次变化正文与错误。稳定已结束项留紧凑身份、终态、结果绑定与原件入口，不重发请求全文和尾日志 |
| `changes` | 新决策事件、状态／绑定／结果变化和删除／解决事实；给实际变更值或可读取的完整变更段，旧绑定不得被无声覆盖；不交付一个哈希要求 Agent 猜正文 |
| `evidence`、`coverage` | 原 observation 当前身份、原件／本输入记录定位、返回范围、未返回部分、后续定位及各集合完整性；partial／corrupt／失败原样列出 |

保留请求拒绝的完整 code／message／next_action 和原 receipt；`cq-input-rejected` 是拒绝，
不是等待确认。原工具 `ok=false` 及源读取 limitations 必须进入 changes／当前阻塞。
报告必须携带 operation/run/mode、question selection、freeze/checkpoint/model/profile 的现有
request binding、report path/digest、valid／validation_errors 及原有结果限定。
`no_new_report`、`new_report_rejected`、`ambiguous_new_reports`、`superseded` 不合成成功。
进程 exit、work_state、实际报告和语义裁决分别呈现，不以单一 completed 归并。

删除／解决变化保留被删除项的身份和最后绑定；纯 heartbeats、日志增长、观察时间／页窗口变化
不构成决策。噪声去除限定在已知运行元数据位置，不能递归删除业务字段中同名的
`evidence_refs`、时间、ordinal 等。未知字段的非噪声变化给准确字段定位与变化原文，
不因字段不在短表中静默丢掉。app-server 通知沿原例外保存在 raw observation，不作决策事件。

正常输入预算为 **32KiB UTF-8 JSON**，是展示分页预算，不是总业务范围、授权或内容写入硬门。
不够时按固定顺序提供用户控制／未知写入／首阻塞、未决／新失败、阶段／成果绑定及其他变化，
剩余内容沿 §5 补读：覆盖对象先分组，过大的单项以身份及准确引用占位，绝不截成假完整正文。
封装元数据本身超预算时同样分页，不规定 run/operation/待办数量上限。coverage 明确每个
集合 total/returned/complete 和继续位置；拿不到 total 时标 unknown。Delivery 在依赖未返回
集合的动作前读完对应集合；例如未知写入集合未完整取得时不能认定可重试、交接或收尾。
输入分页需读取的费用归本条净成本，不把搬去补读的字节算成已经节省。

### 3.2 事件去重与待投递变化

复用 `(run_id, source, byte_offset)` 事件身份，结合源内容身份验证；`get_run_events.line_no`
在每次扫描中重新开始，只用于该页展示。事件页跨页重复不重复注入；同位置内容变化、
源缩短／损坏或工具失败仍保留为异常，不让原去重掩盖真实错误。

唤醒比较以当前决策状态及新事件为依据，`changes` 相对最近**原生 API 已确认接收的输入**，
不是最近一次 observe。重复观察可以覆盖最新 raw observation，但不得推进模型投递基线。
API 接收不等于 Agent 已消费、动作成功或业务裁决，继续沿现有请求回执核对。

busy 期间用户输入优先，原 message_id/source/order/control 处理不改。
若观察 E1 后又观察 E2，待投递包保留 E1、E2 两组新事件／结果，当前状态可更新为 E2；
opened→closed 这样的短暂问题用两次实际变更或原事件引用保留，不能只给最终 closed。
不把多个未投递包简单拼成无界输入：待交付变化列表同样分页。一次成功 send/steer 只
确认该包实际覆盖的范围，其余继续待投递。turn 结束 race 保留原包给 idle 路径。

投递所需最小状态放入已有 `session.json`（事件读取 cursor、已投递范围及待投递输入定位），
完整决策变化包先追加到已有 `session-events.jsonl`，附 byte_offset/byte_length/digest；
不另建快照库、请求账本或恢复服务。只有决策变化才追加包，不把每次心跳 raw observation
全量归档到此处。包存实际变更与必要当前状态，业务大原文继续引用原文件。
记录投递尝试／API 接收／未知沿同一 session-events；原子保存 session.json。
内部读取事件页不能在 raw observation 和待投递变化尚未留存时提前永久推进 cursor；
调整现有 `_observe_run_events` 的保存时点至本次 observation/变化包留存后。
接续时重建当前必要状态，并合并未确认输入定位；journal 已留存而 session 保存中断时，
以 journal 中相应投递记录核对，不凭 cursor 或 wake_count 推定已送达。send/steer 回执
不确定时标 delivery-input unknown，不重放平台动作；重送状态须明确是可能已接收的观察。
这只是原投递路径的必要内容保全，不提供自动重启、重开 run 或新增建模轮次。

## 4. 请求账本与 operation 投影

每次观察继续读取完整最新 `control/host-requests.jsonl` 并保存原始内容及读取失败。
内部读取不沿“模型一次全文最多 2MB”的显示限制：大账本允许按完整行读取汇集；
超大／半行／损坏明确标覆盖不完整，未读部分及源定位保留，不能把缺失请求当已完成。
不因全文较大返回原来一句“use incremental run events”后继续当请求集合完整。

按 request_id 聚合账本行，仅为定位已有真实提交。正文及重复提交行留在原件；
无 request_id 的遗留行保留 uncorrelated 和范围引用，不能与任一已知请求强配或视为零请求。
结果以同 run 原 receipt／`get_request_result` 的既有判据为准：digest 冲突、终态无回执和
FIFO 消失无回执仍分别是 conflict／unknown，提交成功仅 submitted。
可在 Delivery 内复用现有 receipt 解析／结果函数，不能通过“最后一条账本”自行认定 consumed。
已完成请求不重复调用结果工具；新增/变化的 receipt 仍从原增量事件捕获，binding 变化仍唤醒。

活跃、submitted、unknown、rejected 尚需处理、遗留无法关联项默认保留；真正已结算项
不重发正文，但保留 request_id/action/outcome/digest 与 ledger/receipt 原件定位。
历史结算列表分页可读，正常默认页只给数量和索引入口；恢复首包仍有完整未决集合及结算
索引，不能要求模型从旧上下文记住 100 个终态。operation 使用同样规则：活跃／未验证项
完整绑定，稳定终态历史采用分页紧凑索引；本次终态变化必须送达。

operation 当前控制与 consult 回执保留新正文和未决内容，不以“历史操作结束”隐藏仍需
处理的用户输入。错误只有日志内可见时不靠 regex 猜业务失败：状态非零退出、原工具失败
或已知 error 字段触发准确日志定位及补读；未知日志事件仍按 §3 给变化原文／引用。
仅日志增长本身不触发推理，程序存活观察继续。

## 5. 有界原件读取

### 5.1 扩展现有工具，不建立通用查询语言

`read_delivery_artifact` 保留 `{path}` 全文方式（原 2MB 模型响应上限），显式增加
`source_ref`、`selection`、`max_bytes`。`max_bytes` 默认／最大均为 **16,384**，沿现有
handoff 字节分页；全文方式不伪装成分页，不改变旧返回 text/content_digest 的含义。

- `source_ref`：path、scope、byte_length、content_digest。scope 为 `file`（普通/可替换文件
  完整字节）或 `prefix`（确定性的已捕获 append-only 文件前 N 字节）。从程序对**实际读取
  内容**签发；调用可先只给 path+selection，响应即提供当前 source_ref，后续必须带原引用。
  不信任模型宣称某个可变 JSON 文件是 append-only；prefix 仅适用于既有 JSONL 日志/账本。
- `selection` 二选一：`{kind:"bytes", offset:0}` 读取精确 UTF-8 字节页，适合段落、日志及
  事件（程序给 event byte_offset/byte_length）；或 `{kind:"json", paths:[["reports",0,"verdict"]],
  offset:0}` 对 JSON 做精确结构字段选择后按字节分页。paths 最多 16 项、每条最多 16 层，
  段仅是 literal key 或非负数组下标；无 wildcard、递归、过滤、排序、JSONPath 或业务运算。
  空 paths 不合法；全文读用原方式。无特殊 JSONL 查询：请求／事件定位沿已有源字节位置，
  可读取一行的区间并分页；不了解定位时先读有界字节段，不通过文本 grep 推断结果。
- bytes 可附 `length` 固定待读区间；不提供时至 source_ref.byte_length。事件一行很大时仍
  可在该精确区间继续；JSON 字段中很大的一个值按序列化 UTF-8 页返回，不截掉值或伪装
  成合法完整 JSON。续页绑定相同 source_ref、selection 和原序列化顺序，沿 next_offset 读。

返回 source_ref、实际 selection／returned_range、text、next_offset、read_complete、
source_complete、omitted、limitations。`read_complete` 只代表所选范围全部返回；
`source_complete` 只有所选为全文件且完整返回时为 true。精确字段读取即使读完也明确
“其余字段未返回”；分页 text 在完整拼接前不当作完整 JSON 解析或业务判据。
JSON 采用确定性序列化及固定 paths 顺序，续页参数不可变。无 token 数猜测，字节预算不
称为 tokenizer 上限或节省 token 数。UTF-8 边界规则复用 handoff，个别码点超过剩余字节
时按原工具最小完整码点规则返回并说明实际字节数，不破坏中文。

### 5.2 身份、漂移及准确定位

普通可变文件引用核验完整 digest；observation.json 被替换时旧引用返回
`artifact_changed`，提供当前可读身份／重新定位方式，不返回新内容冒充旧版本。
旧 observation 仅作当时观察，后续决策变化包与原事件/报告仍可按已留存原件读取；不承诺
保存每次 raw observation 旧副本。不可变 handoff 包继续使用其原 material_id/path/digest。

append-only 源引用固定捕获的前 N 字节及其 digest；追加不使本页或续页失效，本次
source_complete 只对该捕获范围声明，新增内容在下一当前引用中读取。前 N 字节改写、
缩短、换文件内容不符则 artifact_changed。事件的精确位置是 source byte_offset 加实际
byte_length，不使用扫描页的 line_no；普通事件目前没有 byte_length 时读取源原行求得，
truncated placeholder 本来就给 byte_length。partial line 不当完整事件。
原文件摘要必须取同一次读到的字节，不能先 hash 再读正文而错绑版本。

读不到／坏 JSON／非法 selection／UTF-8 错误分别返回可定位 `artifact_unavailable`、
`artifact_corrupt`、`artifact_selection_invalid`；给 path、所选范围、retryable 与 next_action。
`artifact_forbidden` 不返回未授权内容或其 digest。错误只是当前补读失败，run 可继续修正。
字段不存在与值为 null 分开报告，损坏 JSON 可用获准 byte selection 查看实际原字节；
不能从 parse 失败推断没有错误／没有请求。JSON 字段分页若源变化先失败，不混拼两版本。

### 5.3 权限与实际缺口

复用 `_read_artifact` 当前 sources、绑定 run 私有目录、session 原件、获准修复结果集合。
仅补齐被本 session 跟踪的 operation 返回的 **record_path、logs 中 stdout/stderr 路径**和
本 session repair_verification 已生成结果路径；从真实 operation/session 记录验证身份，
不是批准 `.delivery-ops/` 全目录。无对应 operation 登记、相邻 operation、符号链接越界仍拒绝。
该补齐是移除默认尾日志后准确补读的必要路径，不扩大修复 executor、生产或代答者权限。
隐藏 CQ／Judge 原件仅供已有可信 Delivery 读取；其引用、字段选择、摘要和变化包保持
Host 私有。不自动发布 handoff 包，不生成生产公开投影或混入 public-messages。
跨角色转发仍走 `_assert_material_route`／原公开投影，读取成功不授予转发权限。

## 6. Delivery 的实际使用与角色边界

提示更新同时落到实际加载的 instructions 与 delivery skill：默认先看状态、coverage 和
引用，针对决策缺口补读；不要反复读取整个 observation／ledger 来确认等待。
必要全文仍可通过旧全文或逐页完整读取取得，不设置只能读一次的门槛。

- CQ 审核：取当前 review/draft/version/digest，读本次待审问题、必要业务依据及相关确认，
  逐项给实际理由。精简状态不证明完整题池已审、已冻或 handoff-ready。
- 首链公开反馈：读当前 Coordinator 阶段确认与绑定 applied Attempt/版本，再沿原获准
  checkpoint/freeze/question selection 组织反馈；读完选定问题的 Consumer 实际回答、
  读证及完整反馈，失败/unknown/superseded 显式处理。不复制整轮历史，不再做 Judge 工作。
- 故障／修复：读取确切事件、receipt 或日志范围，保留第一失败层及原 operation；只从
  公开证据生成获准修复任务，不能把私有 Judge 原文或引用传给修复者。
- 最终结果：精简包只供导航，沿既有报告资格核验及真实独立裁决交付；未知写入、未返回
  关键集合、报告缺失或无效仍未完成。dry-run/apply、原子性、实际读回、完整冻结分母不变。

同步两处原“Read the complete original events and receipts”措辞，明确为**当前判断所需的
完整原事件／回执**，必要全文或整题集仍须完整取得，不默认通读全部历史。不会通过删
职责或改变业务含义让输入变短；输入 prompt 与实际工具合同须一起交付。

## 7. 实质决策表

百分比不代表测试概率。本轮没有关键未决业务取舍；常规参数／复用路径有当前证据支持，
明确超过默认 85% 阈值的选择按用户设计授权采用，不写成用户逐项批准。

| 编号 | 采用方案及取舍 | 依据／把握 | 来源与状态 |
| --- | --- | --- | --- |
| D1 | 完整 raw observation＋确定性决策投影；不加 LLM 摘要或状态服务 | 现有 observe/save/input 三处可复用；明确超过85% | 按本轮设计授权采用；完整留存沿权威要求 |
| D2 | 当前未决/未知全覆盖；历史结算紧凑索引；新变化正文可读取 | 原 receipt 判据可复用，避免历史正文增长与结果丢失；明确超过85% | 按本轮设计授权采用 |
| D3 | 默认32KiB输入、16KiB补读分页；超量显式续读，不删关键项 | 复用现有16KiB读取，预算非硬门；明确超过85%，真实净收益待测 | 按本轮设计授权采用 |
| D4 | path-only全文兼容＋字节区间／literal JSON字段；不加查询语言 | 已有路径授权与字节游标；满足段落、事件、结构字段三类补查；明确超过85% | 按本轮设计授权采用 |
| D5 | 普通文件绑定完整digest；JSONL固定前缀身份；原包保持不可变引用 | 防止改版混读，同时避免日志正常追加导致续页持续失效；明确超过85% | 按本轮设计授权采用；版本准确沿权威要求 |
| D6 | 待投递变化合并保全；沿session.json/session-events记录，不增加恢复服务 | 当前pending_observation覆盖及cursor提前保存有实际入口；明确超过85% | 按本轮设计授权采用 |
| D7 | 只补绑定operation/verification原件读取；私有材料不自动转发 | 当前原件权限缺口与去尾日志直接相关；职责隔离已确认 | 按本轮设计授权采用；权限与角色沿权威要求 |
| D8 | A1—A4工程与A5—A6真实净成本/语义效果分开；019提供完整统计口径 | 原需求明确，不以字节减量/设计PASS推出质量或费用改善 | 沿用权威需求，无需重新决定 |

## 8. 实施交接与验收映射

后续获准实施的范围：`modeling_team/delivery.py` 的投影、待投递保全、读取 schema／handler，
两份 Delivery 活跃提示，及其直接单测。原 `host_ops` 结果解析必要时提取/复用既有函数，
不得改结果判据；如无需跨模块变更则不动该文件。`delivery_ops` 原始输出不削减，平台
backend/frontend、model profile、窗口／压缩配置、生产角色不在本条实施范围。

复用 `test_delivery_wakeups.py`、`test_delivery_session.py`、Host request/receipt 和 handoff
现有测试；原“输入等于整份账本”的断言改为 raw 保全、决策完整及按需读回。以下仅为
验收设计，不是本轮测试结果，也不新建一次性阶段输出验收器。

| 需求 | 工程／真实验证内容 | 必须失败的反例 |
| --- | --- | --- |
| A1 | 心跳、日志、页窗口不唤醒；pending/result/phase/user/error/binding变化送达；resume/busy/idle一致 | 业务字段同名被当噪声；E1未投递被E2覆盖；race/未知回执/重启吞掉原事件 |
| A2 | 大于2MB账本、多个run/operation、半行/坏行；未决/unknown完整、已结算不重发；输入与索引分页可读 | 无receipt当完成；digest冲突忽略；超过32KiB默默丢未知写入；operation报告绑定被删 |
| A3 | 中文字节边界、超大单事件/字段、缺字段/null、旧observation、日志追加/改写、selection续页 | 跨版本拼页；partial标全文；用页内line_no定位全文件；日志正常追加使分页永远失败 |
| A4 | CQ依据、公开选定问题完整反馈、报告资格、repair/control/consult原件及授权拒绝 | hidden原文/引用泄露生产或代答；未绑定operation日志可读；摘要/进程退出冒充PASS |
| A5 | 固定同模型/effort、同窗口/压缩、同代码与范围，记录输入、补读、总调用、压缩/未命中和阶段时间 | 只比默认包字节或忽略补读/失败成本；与020/021同时变化却全归022 |
| A6 | 后续另获准的真实Delivery流程、最终完整独立业务验收，保留原问题分母及退步 | 外层补位当自主成功；工程/减量当业务质量PASS；为成本省略依据或未知 |

A1—A4 用本地 fixture、stub runtime 和真实文件读/权限/回执合同核对，不调用外部provider；
必要实际原生接线可连接本地模拟provider，不消耗semantic start。实施后运行受影响Team
定向及全量测试；若实际变更backend/frontend，再执行该侧全量及既有systemd重启/健康验证。
仅Team/指令改动不要求重启平台服务，是否有活跃Delivery需沿原授权在后续启动时加载新代码。
独立工程验收按后续授权安排，不以开发者自测替代。

A5 可先对相同保留观察做离线输入字节/token（有准确tokenizer才报token）对照，但此类
对照只证明序列化差异。真实A5须同范围获准调用，沿R4.3-019统计实际补读、压缩及输出；
不得因019尚未实施阻止实际建模，已有回执不足就PARTIAL。A6独立裁决者不得创建、继续、
修复被验收run或修改证据。当前不新增provider／semantic start授权，也不恢复停止的DeepSeek。

## 9. 检查与独立审阅

2026-10-14 独立 `plan_reviewer`，task `/root/r4322_design_review`，结论 **PASS**，
0 Critical／High，无未决关键假设，无阻塞性修订。实际核验 HEAD 及交接需求／设计
SHA-256 一致；完整输入身份、覆盖和代码依据保存在[审阅记录](../records/2026-10-14-r4-3-022-design-review-record.md)。
Reviewer 未修改文件、执行产品测试、启动服务、调用provider或semantic start，也未读取
隐藏答案。PASS 后仅同步状态及本节记录，设计第2—8节与需求F1—F7／A1—A6未改变。

文档检查覆盖本次新增本地链接／锚点、Markdown围栏、F1—F7／D1—D8／A1—A6及状态
一致性、git diff whitespace和范围；019—021正文与HEAD一致。没有修改产品或活跃提示，
无需backend/frontend测试、技能validator或服务重启。这些检查只证明文档一致性。
设计PASS仅表示可交接实施，A1—A6及真实净成本／质量效果仍须后续独立证据。
