# R4.3-013 共享设计测试与后续验收记录

## 1. 范围与证据

权威范围：[R4.3-013](../../requirements/requirements-v4.3.md#r43-013-agent-自主选择文件或目录引用交接)。
设计：[Agent 引用交接](../designs/2026-10-11-r4-3-013-agent-reference-handoff-design.md)。
基线 `0b73001`；用户本轮授权细化、设计和独立测试。本轮独立测试检查设计可实施性、
需求覆盖、当前调用点及文档合同；不实施产品、不启动服务、Agent 业务运行或外部调用。

| 证据层 | 本轮状态及能证明的边界 |
| --- | --- |
| 作者文档检查 | PASS；相对链接／锚点、编号、围栏、JSON 示例及 diff；仅证明文档合同 |
| 独立设计审阅 | PASS；0 Critical／High，无关键待确认假设，不等于功能验收 |
| 独立设计测试 | Round 1 design-test PASS；T01—T08 静态正常与反例核查通过，不等于运行代码的功能 PASS |
| 开发／独立功能／真实交接／独立语义 | 未执行，需实现及对应授权；设计 PASS 不覆盖这些层 |

## 2. 需求覆盖与反例

| 用例 | 对应验收 | 输入及检查 | 预期／需实施后补证 |
| --- | --- | --- | --- |
| T01 | A1 | 同一普通消息／候选，正文和 body_ref 两种方式；带独立说明与辅助目录 | 原完整内容和业务 digest 一致；说明不拼入正式 JSON；Agent 可继续选正文 |
| T02 | A2 | Modeling 私有文件 → Coordinator；拓扑决定 → Protocol；只读角色／Delivery 生成新材料 | 有实际发布映射／受限读写入口；不要求接收方访问源角色私有路径，不提升只读沙箱或 Delivery 开 shell |
| T03 | A3 | 目录超过一页，正文超过一页，中文字符跨字节边界；选子集／全部 | manifest 固定完整集合；列举和正文独立完整性，cursor／offset 续读无损；不是显示一页就已读全 |
| T04 | A4 | 原 Profile 无边、CQ private → production、隐藏报告 → repair、其他 run、symlink 逃逸 | 原权限制约优先；不泄露受保护目录，不通过引用或 outbox 扩权 |
| T05 | A5 | 已批准候选／计划、正式 report_ref；body_ref 指向目录或缺成员；反向回复槽 | Host 全文解析并进入原 validator／digest／receipt；引用失败不消费槽；typed delivery 身份不断开 |
| T06 | A6 | 源删除／修改、复制中变化、缺文件、snapshot 损坏、撤权、恢复缺包；legacy sink 连续超过三次引用错误 | 定位且可修正；已送旧副本不变；恢复按原 scope 检查；引用错误不进 legacy 报告预算，有效报告仍可提交，不 kill 或自动重放 |
| T07 | A7 | 第 5.2 节全部通道，与当前 tools/list、nativeTool 边界、packet、legacy 提示对照 | 每行具体接入；CQ 不增加 Team 边，Judge 冻结读取约束保持；不存在只改提示的完成声明 |
| T08 | A8 | 发送回执、单文件读全、目录列完、candidate 批准、terminal summary 分别观察 | 不把引用／发送／计数下降当语义 PASS；真实行为及语义质量单列未验证 |

独立测试者应自行读权威范围、设计和相关实际入口，保存逐项事实依据，而不是重复作者结论。
Critical／High 先修订再复测；每轮记录输入版本、失败、修正与最终边界，不覆盖失败历史。
本表预期为后续工程／真实验收意图，本轮只验证设计具备对应完整合同。

## 3. 文档检查

作者执行 `git diff --check`；对变更文档检查相对文件链接／锚点、围栏、JSON 结构示例、
需求 F／A 与 D 决策主表对应。只变更 Markdown，无 backend/frontend 或 Team 可执行改动，
不跑产品全套测试或服务重启。独立测试者可重复必要文档检查并核对当前代码符号。

## 4. 独立轮次

以下保留各轮实际输入、观察、修正及结论；未执行证据不得预填 PASS。

### Round 1 — 独立设计测试（2026-10-11）

- 测试者：未参与起草的 `r4313_design_test`；完成时间 2026-10-11 21:12（Asia/Singapore）。
- 总体结论：**design-test PASS**。T01—T08 的设计合同、当前接入点和反例 walkthrough 通过；
  没有未解决的 Critical／High。该结论不是工程、独立功能、真实交接或独立语义 PASS。
- 代码基线：`0b7300170492d5b9892c8c60acd8c49ba5df475b`；工作区只有本次四份 Markdown
  变更（README、需求、未跟踪设计、未跟踪计划）。测试者仅追加本文件，没有改需求／设计／代码。
- 首次读取设计 SHA-256：`9c9f0f9295ff22cbe46ef936f11c6dbcacaaaf9de1c8b88a5568f3aa59d46ea5`；
  计划首次 SHA-256：`6995d9c98fe68c2b258570696e496e8dc18c82c4624881e47c69d286952f5fbe`。
  本轮过程中作者修订了工具名、只读输出及 legacy 引用恢复合同，最终按下面版本重新核对。

| 最终测试输入 | SHA-256（追加本轮记录之前） |
| --- | --- |
| `docs/requirements/requirements-v4.3.md` | `0efe7ebdafab463129e63076e970e2739534309fa19f93499f5adcf895b221cb` |
| `docs/delivery/designs/2026-10-11-r4-3-013-agent-reference-handoff-design.md` | `0107b15c8e3f951516861e94ce3dac85f5e0d8f9e684f3e28eb44d44519f11de` |
| 本测试计划 | `ec41f263a217ff709e7086f46f5389aaa49515d128119b6eb339ac5fd90c4558` |
| `docs/README.md` | `d86452131cc92f78c6714d8124d7963ae3d04a3aae8e3cb412c6c5eb5870bd89` |

#### 实际检查步骤与证据

1. 执行 `git rev-parse --show-toplevel`、`git status --short`、`git rev-parse HEAD`；
   阅读根 `AGENTS.md`、R4.3-013 及其 R4.3-003／006／007 基础边界、设计与既有 T01—T08。
   本轮只复用该测试计划，没有创建第二份方案或一次性业务验收器。
2. 执行 `rg -n` 定位 `Delivery`、`TeamTransportBroker.send`、`mcp_response`、
   `RuntimeDelivery`、`_observe_formal_candidate_delivery`、`_publish_cq_question_draft`、
   `namespace_command`、`DeliverySession.call_tool`、`V3BatchReportContract.read_frozen_evidence`、
   `ReportSinkServer`；以 `sed -n` 阅读以下具体调用段：
   `transport_mcp.py:469-543,1164-1215,1320-1354`，`runner.py:6081-6183,7170-7240,9950-10110`，
   `runtimes/base.py:35-62`，`runtimes/codex.py:2730-2765,3330-3402,5045-5275`，
   `delivery.py:304-371,372-480`，`runtimes/delivery.py:35-113,130-170`，
   `acceptance_runtime.py:829-986,3400-3520`，`report_sink_mcp.py:400-460,504-548`，
   `candidate_progress.py:569-615`，`host_ops.py:1822-1914,3277-3288`。
   同时核对 CQ Profile 的 communication、Coordinator instructions 第 281 行正文建议要求，
   及 `host_ops_mcp.py` 的公开工具名。这里是静态调用点核查，不声称 GitNexus 图覆盖。
3. 执行 `git diff -- docs/requirements/requirements-v4.3.md docs/README.md`、`git diff --stat`、
   `git diff --check`：只见需求细化／状态索引文档变更，diff 格式检查退出 0。
4. 两次执行终端内通用 Python Markdown 检查：`Path.read_text()` 读取上述四文档，
   `re.findall` 解析相对 Markdown 链接，`Path.resolve().exists()` 检查目标，
   按标题生成保留 Unicode 字母数字的 slug 检查锚点，检查成对围栏，对 JSON 围栏运行
   `json.loads()`；逐表核对 F1—F8、A1—A8、D1—D8、T01—T08 无遗漏或重复。
   最终输出 `files=4, local_links=49, anchors=6, json_blocks=1, issues=[]`，四组编号均 PASS。
   这是通用文档结构检查，不代替下面逐项合同推演。
5. 用 `sha256sum` 固定输入版本；作者修订后重新读取 D7、§5.2／5.3 以及修改的 T02／T06，
   并重新运行必要链接／JSON／编号检查。未运行产品套件、服务、外部模型或真实 Agent。

#### T01—T08 独立结果

| 用例 | 状态 | 正常／反例实际 walkthrough、依据及结论 |
| --- | --- | --- |
| T01 | PASS | 以相同完整候选 C 分别置于 text 和 body_ref，按 §5.1 归一化均为 `Delivery.text=C`；说明另存展示字段，candidate_progress 仍对 C 解码／算业务 digest。仅辅助目录不会注册候选；无引用保留原 schema 行为和 Agent 选择。F1／F5 → D1／D5 → §5.1 → A1 可对应。 |
| T02 | PASS | Modeling 私有 work 文件先由角色路径映射发布，Coordinator 通过 token 绑定 list/read 读副本；拓扑只给 Protocol 获准决定内容，不给地图写权。修订后无文件写入口角色用 scoped `write_handoff_output`，经 Team 原工具／CQ capability／report capability／Delivery dynamicTools，保持 read-only／native 禁用边界。F2／F3 → D2／D3／D7 → §4.1／4.2／5.3 → A2 有实际接入位置。 |
| T03 | PASS | 五成员目录、每页两项时 manifest 必含全部五项，cursor 只分页显示；显式子集只固定选中集合，不隐式混入其余成员。UTF-8 示例 `a中🙂b` 为 9 字节，页可按 offset 0→4→8→9 无损拼接；§4.3 要求实际 offset／next_offset、边界及 read_complete，不能把目录列完或读一个成员当全部已读。非法 cursor／未读完沿 §6 可纠正；具体参数取值校验属实施测试。F4 → D6 → §4.2／4.3 → A3。 |
| T04 | PASS | 无 Profile 边先拒绝；CQ private／reviews 不进入生产源根，隐藏 Judge 报告不能借修复 outbox 传播；其他 run、他人 home、symlink／`..` 与目录混入禁用成员均拒绝。读取身份来自原 socket／token／session；sender 自报 recipient 不扩权，反馈不枚举受保护集合。Delivery 的私有读取权不等于 public repair 传播权，现有 `prepare_repair_task` public_refs／owned_paths 可对应。F6 → D4 → §4.1／4.2／5.2 → A4。 |
| T05 | PASS | 已批准计划／候选／report_ref 保持既有版本、业务摘要及 delivery／attempt 身份；Host 读完整正文再进原 validators，辅助目录多 JSON 不自动合并或猜正文。无成员 body_ref 在消费回复槽前报错；`Broker.send` 当前先校验后记录 `_pending_replies`，Runner typed candidate／handoff／dispatch 继续用同 delivery 身份。report sink 引用适配同时改 child-local bridge 和 Host，不能只改提示或 Host 一端。F5／F7 → D5 → §5.1／5.2 → A5。 |
| T06 | PASS | 源修改／删除不改变已发副本；复制失败不发部分包；旧内容损坏报 digest mismatch 而不重建覆盖；撤权停止新读；恢复缺包重新核对来源和正式绑定，不混入隐藏材料、不自动重放。对 legacy 连续四次材料读取／成员错误，修订 §5.2 明确错误先于 validator／`_rejections`，因此不会触发其现有 `max_attempts` 硬拒绝；修正后可交有效 report。已成功 report 查回执不重复提交，真正旧报告错误仍走原规则。F3／F7 → D3／D8 → §4.4／5.2／6 → A6。 |
| T07 | PASS | 逐行核对 §5.2 八通道与当前入口：Team Broker、result／coordination、Host FIFO／consult_team、CQ 私有 publish capability、Consumer/Examiner packet+proxy、report_sink_mcp+ReportSinkServer、Judge 冻结读取、public repair task。native Team、MCP schema/decoder/tools-list、Delivery dynamicTools、v3 与 legacy `_child_package_assets`/sink 分支均明确须接入；CQ 无 Team 边、Platform Examiner 无原始 source、Judge 不在线查平台保持。F2／F8 → D2／D7／D8 → §2／5.2／5.3／7 → A7。 |
| T08 | PASS | 发布 material_id 只证明副本；send 回执只证明消息；list_complete 只证明列举；read_complete 只证明当前文件；candidate 批准与 terminal summary 分别走原业务／终态 guard。设计 §4.3／5.1／7、需求 A8、测试计划证据层都明确真实行为与独立语义未验证，未以引用成功或字节下降冒充业务 PASS。F8 → D6／D8 → §4.3／7 → A8。 |

#### 本轮观察、修正与未验证边界

- 初稿非阻断问题 DT-01（Low）：§5.2 把现有工具写为 `consult_coordinator`。
  复现：`rg -n 'consult_coordinator|consult_team' modeling_team`；期望列出现有工具，实际只有
  `host_ops.py:3277` 的 `consult_team` 和 `host_ops_mcp.py:770` 的 MCP 入口。
  已报告作者；本轮结束前修为 `consult_team` 并加源码链接，状态 **FIXED**。
  初稿 SHA 与本项记录保留，没有把修订后结果回填为初稿无问题。
- 本测试者未报告 Critical／High。作者根据独立审阅反馈补充的只读输出及 legacy 预算隔离，
  本测试者已沿实际 sandbox／sink 独立复核；不是未经核查直接采用作者结论。
- **未执行／不能判 PASS**：接收环境真实可读、原文字节／目录跨页无损的执行验证、正式处理等价的
  工程验证、撤权／checkpoint 实际恢复、native/MCP/legacy 工具加载、提示 validator、真实角色是否
  选引用及返工变化、独立业务语义验收。解除条件为获授权实现完成、运行相应测试及另行获准真实运行。
  这些不属于本轮设计完成门；本轮没有 BLOCKED 的设计用例，也不把上述未执行项当功能通过。
- 建议：无需为本轮设计测试发起产品修复；可将当前设计交给需求开发 agent，后续实现后复用本文件
  进行工程／独立功能测试。是否实施或开启下一轮由主 agent／用户决定。

#### 独立设计审阅结果（与上述独立设计测试分开）

| 证据层 | 执行者／来源 | 实际结论与边界 |
| --- | --- | --- |
| 独立设计审阅 | 未参与起草的 `plan_reviewer`；主 agent 于本轮转交其修订后定向复核结论 | **PASS**；0 Critical／High，无关键待确认假设。复核范围为只读输出权限、legacy 材料错误与报告预算隔离等设计修订；不证明已实现或真实运行。 |
| 独立设计测试 Round 1 | `r4313_design_test`，实际命令与 T01—T08 结果见本轮记录 | **design-test PASS**；静态调用点和正常／反例 walkthrough、文档合同检查通过，真实功能与语义边界仍未验证。 |

本测试者没有代行 plan_reviewer；审阅结论来自主 agent 转交，独立设计测试结论由本测试者自行产生。

### 最终状态回填复核（2026-10-11 21:15，Asia/Singapore）

- 结论：**PASS**；仅复核 Round 1 完成后的元数据，不新增功能测试轮次，不重跑 T01—T08。
  需求顶部／索引／末尾、设计 §1、README 013 状态及本计划证据表均与实际审阅 PASS、
  Round 1 design-test PASS 一致，仍明确未实现／未验证真实功能与语义质量。
- 实际步骤：`sed -n` 阅读上述状态段，`sha256sum` 固定下面输入；用终端内 Python
  将需求／设计／README 的已知状态替换还原为 Round 1 原状态，重新计算 `hashlib.sha256`，
  三份均精确匹配 Round 1 输入 SHA，证明其非状态正文没有改变。测试历史没有覆盖。
- 文档检查：再次执行相对链接／锚点、围栏、JSON 检查和 `git diff --check`，通过；
  无产品代码、服务或外部模型执行。测试者完成本次记录后停止写入，交主 agent 提交。

| 最终元数据输入 | SHA-256 |
| --- | --- |
| `docs/requirements/requirements-v4.3.md` | `8e7ff40d9d07c00e846ccf7a04a866dce472f59ac8590d3c07c7ed14bfcff279` |
| `docs/delivery/designs/2026-10-11-r4-3-013-agent-reference-handoff-design.md` | `e0c162476853080d10b049cb1e3bad806963448e44d67c8dd60b09fc8c0291ae` |
| `docs/README.md` | `2eb568afbe3911212ef58e94848109bac2969a9b4389b3be6f2ce6e120e6ceb7` |
