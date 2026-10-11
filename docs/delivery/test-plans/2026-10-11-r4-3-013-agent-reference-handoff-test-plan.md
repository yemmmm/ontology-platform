# R4.3-013 共享设计测试与后续验收记录

## 1. 设计阶段范围与证据（历史）

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

2026-10-12 当前工程状态：用户后续授权按设计实现并测试，开发完整 Team suite 2660 passed／
11 skipped；独立功能 Round 2 FAIL，窄修后 Round 3 PASS，历史与实际证据见下方各轮。
真实角色自主选择及行为改善、独立业务语义质量仍未验证。

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


### Round 2 — 独立工程功能验收（2026-10-12）

- 测试者：未参与实现的 `r4313_functional_test`；完成时间 2026-10-12 01:03（Asia/Singapore）。
- 总体结论：**FAIL**。相关测试 **237 passed**；独立参数／实际 Broker→Runner→Runtime
  探针另发现 FT-01（Medium）和 FT-02（High），因此不能用已有测试全绿代替 A1—A8 的功能通过。
  本轮未修改产品或测试代码，只追加本记录并保存 gitignored 工程探针与日志。
- 本轮新增授权来自用户“根据设计实现 R4.3-013 并通过测试”；上文设计阶段“不实现”是历史范围。
  不启动 semantic modeling、不调用 provider、不消耗额度；真实角色自主选择、搬运量／返工效果及
  独立业务语义质量均未执行，不把这些未授权事项列为工程 BLOCKED。
- 输入基线：`954f1601e3a79787adfaf929b16bd0edc548b2c3`；Team 48 个变更文件的稳定工作区
  SHA-256 为 `5ea8f8cc0120a1377accd526f5c221cb86dd8521454a06da4b1bcd34779f7a03`。
  逐文件清单见 `workspaces/r4313-engineering-20261012-_snp9c75/implementation-snapshot.json`；
  收尾重新计算所有 48 文件 SHA，输出 `implementation_snapshot_unchanged True files 48 changes []`。
  主 Agent 可同步其他交付状态文档，本轮产品输入始终不变。

#### 实际步骤与执行结果

1. 阅读根 `AGENTS.md`、R4.3-013 的 F1—F8／A1—A8 和 R4.3-003／006／007、已通过审阅的设计、
   原 T01—T08；复用本文件，不另建测试方案。用 `git diff`、`rg`、`sed` 逐入口查看 helper、
   Broker／Runtime、Runner CQ／outer／coordination／checkpoint、Delivery、report sink、read proxy、
   Codex child packet 和实际提示／MCP 工具清单。
2. 在 `backend/` 执行：

   ```bash
   env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_handoff_materials.py ../modeling_team/tests/test_r4313_acceptance_refs.py ../modeling_team/tests/test_r4313_delivery_checkpoint.py ../modeling_team/tests/test_v43_judge_references.py ../modeling_team/tests/test_r3011_runner_wiring.py ../modeling_team/tests/test_r3012_platform_responses.py
   ```

   实际 **127 passed in 9.72s**，exit 0；日志
   `workspaces/r4313-engineering-20261012-_snp9c75/independent-functional-pytest.log`。
   覆盖真实临时文件／Unix socket／MCP stdio 子进程／FIFO、CQ 原 capability、legacy 超三次材料错误后
   仍能成功提交、Judge 冻结续读产生原 receipt、read-proxy facade 保留原 evidence handle 并返回可读 ref、
   Delivery session/run 重新绑定、private CQ 可审阅但不能给 production/repair、实际 Runner checkpoint collector。
   native factory／清单用本地 runtime fixture 验证，未连接远端模型。
3. 同目录执行必要相邻回归：

   ```bash
   env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r23005_issue_escalation.py ../modeling_team/tests/test_r30015_checkpoints.py ../modeling_team/tests/test_r3011_acceptance_cli_flow.py
   ```

   实际 **110 passed in 20.36s**，exit 0；日志
   `workspaces/r4313-engineering-20261012-_snp9c75/independent-adjacent-regression.log`。
   原 phase／terminal／owner／checkpoint／CLI 边界保持；这些旧用例未覆盖本轮新增 coordination refs，
   原 evidence 用例也未断言新增默认字段后的实际保存，不能据此否定下列探针。
4. 独立 helper/checkpoint 边界探针（真实临时目录，原保存／恢复函数）：
   发布目录后新增 `b.txt`，原 manifest 仍只列 `a.txt`；未知 actor 被 `material_forbidden` 拒绝且错误
   不含成员名；保存真实 material artifacts 后撤销 publisher 的 recipient grant，恢复报
   `CheckpointError(reason_code=material_binding_changed)`，未产生可用当前绑定。
   三项 PASS；输出 `independent-boundary-probe.log`。原完整 checkpoint 回归同时覆盖缺包／摘要与
   恢复状态约束；没有借助新增恢复机制或重放生产内容。
5. 当前仓库根执行工程复现（无模型调用）：

   ```bash
   PYTHONPATH=. backend/.venv/bin/python workspaces/r4313-engineering-20261012-_snp9c75/coordination-reference-probe.py
   ```

   保留首次分别复现的 `independent-coordination-probe.log`、
   `independent-coordination-runner-probe.log`，以及补充 body／aux 两种路径的
   `independent-coordination-combined.log`。脚本是真实 helper/Broker/Runner 方法的本地工程探针，
   adapter 只收集 RuntimeDelivery，没有构造业务预期答案或一次性语义裁判。
6. 实际提示与工具合同核查：各现行角色建议正文／引用自主选择；Team `summary_ref` 与消息
   `body_ref` 分开，CQ 经原 capability 无新 Team 边；Delivery dynamicTools 不提供 shell，
   child thread 仍 `read-only`／`default_tools_enabled=False`；Source 才有 approved_sources，
   Platform child 只有自己 packet／代理能力；Judge 原 frozen reader 保留。
   `git diff --check` exit 0。此次只有 Team 变更，无 backend/frontend 变更，不要求产品套件／重启。

#### T01—T08 / A1—A8 本轮结果

| 用例／验收 | 结果 | 实际依据与边界 |
| --- | --- | --- |
| T01 / A1 | **FAIL** | 普通 `send_team_message` body_ref 与内联内容进入相同 pre-send validator，说明独立且 Runtime 不重塞正文，终态 summary_ref 也恢复原完整摘要；但 coordination 的无 text 引用输入与清单不一致，见 FT-01。 |
| T02 / A2 | **FAIL** | helper 私有文件、Delivery 动态 call_tool、真实 FIFO、CQ socket、Consumer／Judge stdio 可写私有输出／发布／列读；coordination 的辅助目录引用被 Runner 丢失，接收 Runtime 无入口，见 FT-02。 |
| T03 / A3 | PASS | 205 文件目录跨页且子集固定；`a中🙂b` 大正文以 3 字节页无损拼接，非法 UTF-8 offset 拒绝；目录列完与文件读完分开；Judge 部分／累积读取只有完整范围才取得原 receipt。coordination 重塞大正文归 FT-02，不据此声称全通道完整。 |
| T04 / A4 | PASS | 无 Profile 边／未知 actor／跨 run／symlink／`..`／窄授权目录成员拒绝；Coordinator scenario-map/joint-acceptance 不给 Protocol，决定 outbox 可给；CQ private 与私有 outbox 不进生产／repair；受限 Source 与 Platform packet 映射已核对。 |
| T05 / A5 | **FAIL** | 正式 Team 正文身份、坏 member 不消费 reply slot、CQ 原 validator、报告原对象／content digest、代理原 evidence handle、冻结原 receipt 已执行通过；新增 CoordinationMessage 默认字段导致原 coordination evidence 全部被 strict 字段集过滤，见 FT-02。 |
| T06 / A6 | PASS | 源删除／修改不改变已发内容，复制期间变化无可用 package，snapshot/manifest 损坏 typed error，当前成员撤权拒读；实际 checkpoint collector 包含普通 material 与 CQ 私有投影、拒 acceptance 私有包；恢复保留原 manifest 并核对当前绑定、撤权恢复拒绝。legacy 四次材料错误不消耗原 `_rejections`，之后报告成功。 |
| T07 / A7 | **FAIL** | Team/summary/Delivery/Host/CQ/Consumer/Examiner/Judge/repair/checkpoint 的真实入口、MCP schema、stdio/native 清单及提示已核对；coordination 当前只改 Broker／schema，Runner 队列、Runtime 与 evidence 不保留新增字段，故覆盖清单不能通过。 |
| T08 / A8 | PASS | 发布／发送／列完／单文件读完／formal guard／Judge original receipt 的不同状态已分别断言；237 个测试 PASS 不能掩盖独立探针 FAIL，不声明真实自主选择或语义质量 PASS。 |

#### 缺陷及修复建议

- **FT-01 — Medium，STILL FAILING：`send_coordination` 可选正文与实际解码不一致。**
  - 前置：真实 store 注册 modeling→coordinator；使用 scoped output 保存文本并成功发布，取 body_ref。
  - 步骤：`mcp_response` 调用 `send_coordination`，参数仅为 recipient_id、message_kind、generation、body_ref，省略 text；同一输入补 text 再试。
  - 期望：工具清单已移除 text required，因此无说明时使用默认定位说明，原正式正文和 phase 仍校验。
  - 实际：省 text 报 `coordination message is not allowed by frozen Profile`；补说明成功。
  - 定位：`transport_mcp.py` 的 `mcp_response` 将 `args.get("text")` 的 None 送入 `send_coordination` 原 str 校验；schema 与 decoder 不一致。
  - 证据：`independent-coordination-probe.log`、复现脚本及 combined log 的 `no_text_result`。

- **FT-02 — High，STILL FAILING：coordination 引用未到 Runtime，原协调证据丢失。**
  - 前置：真实 helper/Broker，Broker 原 `coordination_event_observer` 绑定 Runner 方法，原 phase callback 返回 generation=1；adapter 仅收集实际 RuntimeDelivery。
  - 步骤：①带简短说明与 body_ref 发 `ready_for_acceptance`，正文为 120000 字节中文；②另一次新 Broker 发同通道 text+material_refs；均调用 Runner 原 observer/drain。
  - 期望：原完整 text 用于 phase；Runtime 接收说明和可读 ref，保留 message_id/generation，原 evidence 记录不中断；aux refs 同样可读。
  - 实际：body 模式 `runtime_body_ref=null`、`runtime_material_refs=[]`、`runtime_has_reference=false`、
    `runtime_repeats_full_body=true`、Runtime 120170 字节；aux 模式同样没有入口。
    两模式 `coordination_evidence_count=0`，message_id 仍 `coordination-1`。
  - 定位：Runner `_coordination_transport_event_observer` 队列只取旧字段，
    `_drain_coordination_runtime_deliveries` 只用 full text，丢 display/ref；
    `_append_coordination_transport_event` 的 `set(event)==expected` 拒绝 CoordinationMessage 新增的三个默认字段，
    所以原 inline 的 evidence 也受影响。
  - 证据：`independent-coordination-runner-probe.log`、`independent-coordination-combined.log` 与源码调用点。

本轮没有其他已确认阻断。建议让需求开发 Agent 窄修 FT-01／FT-02，并新增覆盖实际
MCP→Broker→Runner observer→Runtime／evidence 的回归；保留原 phase 语义、message_id、generation
与严格业务校验，不以缩减断言或只修工具展示代替。修复冻结后在本文件追加 Round 3，优先复测
两个失败及所影响的原 inline/coordination/terminal 边界，不重复全部平台或 Team 套件。
本测试者于本轮记录完成后停止写入，交主 Agent 决定修复和复测。


### Round 3 — FT-01／FT-02 独立复测（2026-10-12）

- 测试者：原独立测试者 `r4313_functional_test`；完成时间 2026-10-12 01:14（Asia/Singapore）。
- 总体结论：**独立工程功能 PASS**。FT-01、FT-02 均 **FIXED**；原失败日志和 Round 2 FAIL 保留。
  本轮没有 STILL FAILING、REGRESSION 或工程 BLOCKED；未执行真实模型行为与独立业务语义验收。
- 输入：基线 HEAD 仍 `954f1601e3a79787adfaf929b16bd0edc548b2c3`；冻结的 Team 49 文件 digest
  `c3c70dd30ff8d25c0142d636da8a9097d00fff926916fcec21c9c442baa5bc2e`，清单为
  `workspaces/r4313-engineering-20261012-_snp9c75/implementation-snapshot-ft-fixes.json`。
  独立逐文件 SHA 核对通过；相对 Round 2 只有 `runner.py`、`transport_mcp.py` 和新增的
  `tests/test_r4313_coordination_refs.py` 变化，其他通道复用 Round 2 不变输入证据。

#### 实际复测与证据

1. 独立查看修复代码和新增回归：省 text 时 decoder 提供空字符串，原引用归一化生成默认定位说明；
   原 phase callback 仍消费完整正文；Runner 队列／Runtime 保留 display、body_ref、material_refs；
   evidence 接受限定新增字段，保留原 full-text SHA 和 message/generation。引用模式的 MCP 返回过滤
   phase_event 中的 text/objective 展示重复，但 Broker 正式 phase_event 与 inline 返回不变。
2. 原独立复现脚本未经修改，仓库根执行：

   ```bash
   PYTHONPATH=. backend/.venv/bin/python workspaces/r4313-engineering-20261012-_snp9c75/coordination-reference-probe.py
   ```

   exit 0；日志 `workspaces/r4313-engineering-20261012-_snp9c75/independent-round3-original-probe.log`。
   body-only 原拒绝变为 PASS，Runtime display 229 字节且保留 body_ref；aux-only 182 字节且保留
   material_refs。两模式 `runtime_has_reference=true`、`runtime_repeats_full_body=false`、
   `coordination_evidence_count=1`，原 delivery_id 仍 `coordination-1`。
3. 在 `backend/` 执行受影响测试和必要相邻回归：

   ```bash
   env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4313_coordination_refs.py ../modeling_team/tests/test_handoff_materials.py ../modeling_team/tests/test_r23005_issue_escalation.py ../modeling_team/tests/test_r4313_delivery_checkpoint.py ../modeling_team/tests/test_r3011_runner_wiring.py
   ```

   **81 passed in 6.94s**，exit 0；日志
   `workspaces/r4313-engineering-20261012-_snp9c75/independent-round3-affected.log`。
   新四模式 body-only／body-explained／aux-only／inline 经实际 MCP handler、Broker、原
   CoordinatorPhaseController、Runner observer/drain 和 Codex renderer：formal text／phase_event
   full text 一致；正文模式返回不含 120000 字节正文，实际 renderer 小于 2000 字节；接收 Coordinator
   通过原 MCP list/read 无损取得全文；原 text SHA、message_id、generation、terminal=False／settles=False
   保持；错 generation 拒绝，第二次 drain 不重复投递；inline 展示、返回与 evidence 保持原行为。
   同时重测 UTF-8 分页、reply slot、terminal summary guard、Delivery/CQ 隔离／checkpoint 及原 phase 回归。
4. 最终再核对 49 个文件 SHA 与冻结清单一致；`git diff --check` exit 0。只追加本测试记录，
   不修改产品、测试代码或其他交付文档；没有 provider、semantic run、服务重启或额度消耗。

#### 最终 T01—T08 / A1—A8 状态

| 用例／验收 | 状态 | 本轮结论依据 |
| --- | --- | --- |
| T01 / A1 | **FIXED → PASS** | 无 text 的 coordination body_ref 成功，说明不污染正式内容；其余正文／引用等价复用 Round 2，并重测普通 Broker 与 summary guard。 |
| T02 / A2 | **FIXED → PASS** | coordination body／aux refs 到实际 Runtime，Coordinator 原 MCP 入口可列读全文；其他私有生产、Delivery、CQ、Consumer／Judge 环境沿 Round 2 通过。 |
| T03 / A3 | PASS | 本轮 UTF-8／大目录 helper 及 coordination 接收无损续读通过；Judge frozen 完整范围 receipt 复用不变输入证据。 |
| T04 / A4 | PASS | 本轮普通权限／reply、Delivery private CQ、CQ 私有与 Coordinator map 隔离回归通过，其他跨 run／路径边界复用 Round 2。 |
| T05 / A5 | **FIXED → PASS** | coordination evidence 恢复原 message/generation/full-text SHA，正式 phase 仍取全文；原 candidate/report/proxy/frozen receipt 身份复用不变证据。 |
| T06 / A6 | PASS | helper 撤权／损坏／变化、Delivery checkpoint 当前绑定回归通过；legacy 重试预算、完整 checkpoint／缺包边界沿 Round 2。 |
| T07 / A7 | **FIXED → PASS** | 新 coordination MCP→Broker→Runner→Codex 接入与清单一致，无新增边；其他 native/MCP/legacy packet、工具及实际提示均未变，沿 Round 2。 |
| T08 / A8 | PASS | 独立工程功能通过与开发全套、真实交接行为、独立业务语义分别表达，不用文件读取、字节下降或本轮 PASS 推导语义质量。 |

建议主 Agent 可按本轮独立工程功能 PASS 完成授权的工程交付；真实 Agent 是否自主选引用、
实际搬运／返工改善和独立业务语义质量仍未验证，需对应真实运行授权。测试者本轮完成后停止写入。
