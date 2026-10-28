# v5 P0 独立工程功能测试

日期：2026-10-28。关联：[v5.0 需求](../../requirements/requirements-v5.0.md) R5.0-001／002／004、
[实施计划 P0](../implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#5-p0在全面改造前验证什么)。

## 范围与边界

本测试由未参与本批实现的独立工程测试 Agent 执行。仅核查 `modeling_team/v5/` 的工作空间版本、
操作幂等、自然回合边界控制、MCP 输入／权限边界和恢复合同，并运行该包自有测试。
不启动收费模型，不创建平台业务资源，不变更已有运行与证据，不读取隐藏语义题集或私有语义报告。
产品源码只读；缺陷交主 Agent 修复。测试结果不等于真实模型质量、P0 整体放行或完整 v5 验收。

## 环境与步骤

- 工作目录：`/home/yangxiang/ontology-platform`；本批基线 HEAD：`bb55b86`，测试对象包含当前未提交变更。
- 复用 `workspaces/v5-codex-p0/.venv` 和既有 PostgreSQL 连接文件；数据库测试只创建并删除自己拥有的随机 schema。
- 先检查适用 AGENTS、权威需求、实施计划与变更；复用现有测试，不另建一套测试方案或评分器。
- 运行完整 v5 自有测试；对测试未覆盖且直接关联本次合同的疑点，使用同依赖、独立 schema 的有界重现。
- 只在后续源码变化、失败修复或证据缺口需要时复测，继续追加本文件。

## 用例与通过标准

| 编号 | 复用／补充验证 | 期望结果与通过标准 |
| --- | --- | --- |
| F1 | 包导入、配置、SDK setup 与原生工具范围 | 现有无推理测试通过，不加载旧 Runner，不静默换模型／effort，关闭未授权 Skills。 |
| F2 | 材料范围、哈希、范围读取与结果结构 | 未授权材料不返回内容；变化版本不冒充原件；错误可恢复，结果合法性不替代语义正确。 |
| F3 | PostgreSQL 业务版本与同操作重试 | 并发不覆盖新修订；相同操作返回原回执；不同意图不可复用同身份；旧 checkpoint 不倒写业务状态。 |
| F4 | 暂停／停止、预算信号与排队输入 | 忙碌回合自然结束；全部成员停稳才显示 settled；恢复后排队输入有明确送达／消费记录且不重复消费。 |
| F5 | 未消费输入及控制状态的失败边界 | 未确认消费不能默默丢失或升级为已消费；未知原执行不重复启动，并有可定位状态。 |
| F6 | 独立读取权限 | 隔离 MCP 真实读取获准 PostgreSQL 对象，越权拒绝不泄露内容；平台读取固定 Host 授权范围。 |
| F7 | 平台故障探针及独立交接的合同静态核查 | 不重新实现语义裁判；成功、未写入与未知分开；交接绑定冻结目标，评价只读，公开反馈不含隐藏内容。 |
| F8 | 相关静态检查 | Ruff／格式／diff 检查准确报告；未覆盖或无法运行的项明确记 BLOCKED，不计 PASS。 |

## 测试轮次

### 第 1 轮：FAIL

截至 2026-10-28 08:11 UTC。产品基线 `bb55b86` 加当时未提交的 v5 变更。
**37 项现有测试通过，但增补的合同边界重现发现 2 项 High、2 项 Medium 缺口，因此独立工程结论为 FAIL。**
未执行真实模型或平台资源写入；没有读取私有语义题集、答案或报告。

#### 实际命令与结果

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 pytest -q \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests
```

结果：`37 passed, 1 warning in 8.08s`，无跳过。警告来自第三方 Pydantic settings 的
`lifespan` forward-reference 注解；本轮不将其当作产品功能失败。
这些测试包含真实 SDK setup、namespace 隔离、材料读取合同、真实 PostgreSQL 版本／并发／
同操作重放、checkpoint 权威分离和控制状态；没有 `turn/start` 模型调用。

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff check \
  modeling_team/v5/src modeling_team/v5/tests modeling_team/v5/scripts
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff format --check \
  modeling_team/v5/src modeling_team/v5/tests modeling_team/v5/scripts
```

结果：Ruff check 退出 1，10 项（F401、I001、PLW1510、导入 pytest fixture 的 F811）；
格式检查退出 1，10 个文件待格式化、12 个已格式化。此时主 Agent 仍在开发，记录为提交前待整理项，
不将格式问题混作运行或建模质量结论。

增补重现用同一 v5 环境运行内联 Python：读取公开测试脚本中的 `SCHEMA`，调用真实
`decode_json_result`；在随机 `v5_independent_<uuid>` schema 中调用真实 `WorkspaceRepository`
与 `TaskControl`；调用既有 `compile_model_changes` 比较两种分批。schema 已在 `finally` 中删除，
未触及主任务 schema 或平台资源。实际输出：

```text
ACCEPTANCE_REPORT_SHAPE {"accepted":{"verdict":"PASS","target_revision":999,"cases":[]}}
NULL_DIFF {"changed_fields":[],"actual_content":{"scope":null},"expected_changed_fields":["scope"]}
UNCONSUMED_INPUT {"first_input_ids":["m1"],"second_input_ids":[],"message_status":"delivered","second_admitted":true}
PARTIAL_RESUME_REGROUPING {"initial_batches":[["concept-a"],["concept-b"]],"resume_batches":[["concept-a","concept-b"]],"already_applied_change_in_new_batch":true}
```

#### 缺陷 IFT-001：High，独立报告可遗漏冻结题并发布错误目标的 PASS

- 位置：`modeling_team/v5/scripts/acceptance_case.py` 原第 13—21、62—69 行。
- 重现：从该文件 AST 读取 `SCHEMA`，执行
  `decode_json_result('{"verdict":"PASS","target_revision":999,"cases":[]}', schema)`。
- 期望：根据冻结题分母／唯一索引与目标修订核对完整性；缺失或漂移返回可恢复的报告合同错误，
  不能公开 PASS。此核对只验证可观察身份与覆盖，不代替独立语义判断。
- 实际：上述结果结构合法；`main` 不再核对题目分母、重复／遗漏索引或目标 revision，直接将模型给出的
  `verdict`／revision 与返回数组的长度发布为公开结果，可出现 `PASS / 0 / 0 / revision=999`。
- 影响：V8 的冻结目标／题集绑定不能由当前接线保证；不能以该公开 PASS 作为放行证据。

#### 缺陷 IFT-002：High，跨批部分成功恢复会改变原分批并重带已成功项

- 位置：`platform_graph_case.py` 原第 33—38 行与 `platform_case.py` 原第 103—111 行。
- 重现：以两个通用 Class create 变更调用 `compile_model_changes`，初始 `batch_max_items=1` 得
  `[[concept-a],[concept-b]]`；该探针 `partial` 初段成功应用第一批、拒绝第二批。
  使用公开 CLI 的 `phase=resume, case=partial` 时，graph 把 fault 改为 `normal`，编译限额变为 100，
  结果变为 `[[concept-a,concept-b]]`。
- 期望：恢复沿冻结的原分批／原操作身份对账并复用已成功的第一批；只对已确认未写入的第二批作准确修正。
- 实际：原成功项被放入内容不同的新 Batch。既有 executor 的幂等身份包含完整 items／content digest，
  新组合不能命中旧单项回执，因而此恢复路径可能重复创建已应用概念；不能证明成功效果不重复。
- 证据边界：本轮通过真实编译器及 executor 身份构造源码确认身份变化；按授权未运行该平台写入，
  不声称本轮已在平台制造或观测到重复资源。发现后立即通知主 Agent 暂勿执行这条恢复。

#### 缺陷 IFT-003：Medium，缺失字段与显式 null 的差异被漏报

- 位置：`workspace.py` 冲突返回中的 `changed_fields`。
- 重现：revision 1 内容 `{}`；revision 2 内容 `{"scope":null}`；再按旧 revision 1 提交修订。
- 期望：冲突反馈包含 `changed_fields=["scope"]`。
- 实际：反馈 `changed_fields=[]`，因为 `old.get(key)` 与 `actual.get(key)` 都是 `None`。
  当前内容与修订仍准确，旧写入也被拒绝；缺口限于冲突差异定位。

#### 缺陷 IFT-004：Medium，已送达但未消费的输入在 finish 后失去后续处理路径

- 位置：`control.py` 原第 76—94 行。
- 重现：enqueue `m1` 给 A；`begin_turn(A,attempt-1)` 返回 m1；
  `finish_turn(A,attempt-1,consumed_ids=())`；再 `begin_turn(A,attempt-2)`。
- 期望：未确认消费的输入保持明确未决，并可按原执行／投递证据核对或接续；不能默默忽略。
  对结果未知不要求盲目重放。
- 实际：第二次调用获准且 `inputs=[]`；m1 仍为 `delivered`，已移除原 active 执行，
  现有接口没有正常接续该未消费输入的路径，也没有给下一次准入返回该未决项。
- 证据边界：这是直接控制 API 的失败边界重现；当前成功探针显式确认消费，未在本轮制造真实模型输入丢失。

#### 用例结论与未执行范围

| 用例 | 第 1 轮结果 |
| --- | --- |
| F1／F2 | PASS：现有 setup、隔离、材料及结果测试通过。 |
| F3 | 基本版本／并发／幂等 PASS；IFT-003 的差异反馈 FAIL。 |
| F4 | 已有自然边界／全部停稳／正常消费测试 PASS。 |
| F5 | 原 active 阻止重复准入 PASS；IFT-004 的未消费输入接续 FAIL。 |
| F6 | PASS 于本轮授权范围：真实隔离 MCP／PostgreSQL 越权测试通过；平台读取桥固定 Host project／Ontology 范围。 |
| F7 | 静态及确定性合同核查 FAIL：IFT-001／002；真实平台故障与语义验收由主任务另行执行，本轮未执行。 |
| F8 | FAIL：10 项 Ruff 错误、10 个文件待格式化；未改源码。 |

建议主 Agent 先修 IFT-001／002；IFT-003／004 按当前 P0 控制组件的保留范围处理并明确交付边界。
修复后复用本文件追加第 2 轮，先复测失败边界，再执行受影响回归。未作 P0 整体、业务语义或完整 v5 PASS 结论。

#### 第 1 轮源码身份

以下是取证时 SHA-256，后续修复不得覆盖本轮记录：

| 文件 | SHA-256 |
| --- | --- |
| `control.py` | `3a81b5e2abd4c3e13716e0f6770c0e7940f4d34f3bcac9249860cb525303ba8d` |
| `workspace.py` | `0aba22ed6bd7f34312474c863eeffd38a1ea0c1a91bd60395b8ca3aa39896a22` |
| `acceptance_case.py` | `a3ac381b53b5470350de708fcc0e786edd0e1103d8b39c33c0a02d4ef9fb65f3` |
| `platform_graph_case.py` | `7eb81dc183ee6a6b567b450ae1573929745ddd53ee9c6393bb0d710c2614b4a0` |
| `platform_case.py` | `bfa4fcae072c1f22825957706508a323fe2e1f7e6113ebb206f6f9f9e18829b5` |

### 第 2 轮：PASS（独立工程复测范围）

截至 2026-10-28 08:44 UTC。仍为 `bb55b86` 加当前未提交 v5 变更；复用原环境、原测试文档和
IFT-001—004 编号。**四项原缺陷均已 FIXED；47 项 v5 测试通过，Ruff／格式检查通过。**
没有发现阻塞当前工程测试范围的新回归。本结论不表示 P0 整体、真实业务语义或完整 v5 已通过。

#### 实际命令与结果

运行第 1 轮同一完整 v5 测试命令：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 pytest -q \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests
```

结果：`47 passed, 1 warning in 10.21s`，无跳过。仍仅有原第三方 Pydantic `lifespan` 警告。
新增覆盖包括评价绑定、未确认消费、null 差异及冻结模型修订漂移；测试 fixture 已移至 `conftest.py`。
以真实 loopback HTTP 服务验证授权 scope 固定与修订漂移拒绝，该 HTTP 边界测试不冒称真实平台语义验证。

再次运行原 Ruff check／format 命令，覆盖 `src`、`tests`、`scripts`，结果：

```text
All checks passed!
23 files already formatted
```

#### 原缺陷逐项复测

| 缺陷 | 第 2 轮状态 | 独立证据与结论 |
| --- | --- | --- |
| IFT-001 | FIXED | 真实 `decode_json_result` 后调用当前 `validate_evaluation_binding`：空／漏／重复／越界题号、错误目标修订和矛盾 PASS 均返回类型化 `ResultContractError`。完整负面 `REVISE` 报告原样保留。源码核对确认正式发布之前调用此函数，合同错误反馈给原独立上下文修正，未合法绑定不能到达公开结果写入。 |
| IFT-002 | FIXED | 源码核对 `compiled-definitions.json` 冻结原 request／batches／source_map，恢复直接复用；request 漂移准确拒绝。只读核对已保留 `platform-partial-001` 公共技术原件：冻结两批各 1 项，恢复 0 次提交，首个 Batch／Attempt 身份原样复用，结果仍为 partial。 |
| IFT-003 | FIXED | 在新建并已清理的 PostgreSQL schema 重放 `{}` → `{"scope":null}` → 旧基线提交，准确返回 `changed_fields=["scope"]`，实际新内容保持未被覆盖。 |
| IFT-004 | FIXED | 新 PostgreSQL schema 中重放未确认消费窗口；下一回合显式返回原 `message_id=m1`、`previous_delivery_unconfirmed=true` 与两次投递历史；消费确认后不再返回。未给其他成员转交该目标输入。 |

独立有界重现输出：

```text
IFT-001_REJECT old-empty-wrong-target evaluation_target_revision_mismatch
IFT-001_REJECT empty evaluation_case_coverage_mismatch
IFT-001_REJECT omitted evaluation_case_coverage_mismatch
IFT-001_REJECT duplicate evaluation_case_coverage_mismatch
IFT-001_REJECT out-of-range evaluation_case_coverage_mismatch
IFT-001_REJECT wrong-target evaluation_target_revision_mismatch
IFT-001_REJECT inconsistent-PASS evaluation_verdict_inconsistent
IFT-001_NEGATIVE_JUDGMENT_PRESERVED True
IFT-003_CHANGED_FIELDS ['scope']
IFT-004_RECOVERY {"same_message_id":"m1","previous_delivery_unconfirmed":true,"deliveries":["attempt-1","attempt-2"],"returned_after_consumption":false}
IFT-002_PUBLIC_TECHNICAL_EVIDENCE {"frozen_batch_sizes":[1,1],"initial_status":"partial","resume_status":"partial","resume_submits":0,"total_observed_platform_applications":1,"same_original_batch_attempt":true}
```

IFT-002 只读核对的原件为：

- `workspaces/v5-codex-p0/platform-partial-001/platform/compiled-definitions.json`。
- 同目录的 `summary-partial.json`、`summary-normal.json`、`platform-calls.jsonl`。

该记录说明成功的第一批未因本次恢复被重新提交；**第二批的原明确拒绝仍保留，跨批业务结果仍是 partial**。
后续必须有明确纠正请求，才能推进未写入的第二批；不能把 graph 节点结束记作全部业务应用成功。

#### 回归与仍未证明的边界

- F1—F6 的已执行工程范围 PASS；原并发、同操作幂等、旧基线保护、原 active 阻止重复准入、
  自然边界与正常消费测试保持通过。
- F7 在本轮静态／确定性及公共技术原件核对范围 PASS；没有重新调用真实平台，没有独立制造未知写入或重复效果。
  对真实故障窗口原件的核对不外推为所有故障恢复情形均已验证。
- F8 PASS；本轮仅更新本测试文档，未修产品代码或改动任何保留原件。
- 本轮不读取隐藏语义题目／答案／报告，不评价业务答案；报告覆盖校验只保护身份、分母和结果一致性，
  **不能证明报告的语义判断正确**。真实独立语义结论仍由获准只读评价路径确定。
- 未确认消费的输入现在可定位并接续；接收方仍须按原 message／投递历史核对其实际效果，不能把该标记当作授权重复副作用。
- P0 V3 的全量用量／费用覆盖、P1—P4 产品化与完整需求验收不属于本次独立工程测试通过范围。

建议：本轮四项缺陷可按上述范围关闭，无需为这些已通过且输入未变的检查增加额外测试轮次。
主 Agent 继续处理其真实平台／独立语义剩余证据，保持相应未通过状态。

第 2 轮取证时的修复源码 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `results.py` | `fc2c31f400647f7684fe6226c27db8864c60590a53b996307db84eead358b9f9` |
| `control.py` | `95a5a15dedf6a4df6d6d41540e49fa705577e6a50507c2a81ceb156b3129a3bc` |
| `workspace.py` | `f56704ed721a0a600a6c5fcc1124be68954fc297ce1d7da9c4880219ed104f68` |
| `material_tools.py` | `60cef95b6cbf24c9f5b01be01d7bd81b6621c834ff4441f4048036ab10cc5e2d` |
| `acceptance_case.py` | `178ccc4c957a3395fdc997869c053bab22e35a16b8386dabc22f6f48623b421f` |
| `platform_graph_case.py` | `0b76d1031b44cb5294053ee7e4ece09ebd488653f5c9f71649734d1782c95fec` |
| `platform_case.py` | `1530dc10daecd86feeecd6032f384c99bfdd3dbee62549787b9ee1318c9293cc` |

### 第 3 轮：PASS（实际读取守卫与收尾核对）

2026-10-28 08:47 UTC 起。主 Agent 根据真实运行中“工具存在但没有实际读取材料”的新证据，
为 V8 新增 `verify_required_reads` 并修正权威工具提示。本轮只独立验证这一输入与证据合同，
不读取真实隐藏材料、私有 query 正文或语义报告，不作语义评分；第 2 轮未变的 47 项回归继续复用。

测试方法：AST 提取当前 `acceptance_case.py` 的真实 `verify_required_reads`，以纯工程 JSONL 事件
对象提供 `read_text()`，直接执行该函数。fixture 不包含任何真实业务或评价内容，无模型调用、文件原件改写或平台请求。
同时静态核对首次发布前和合同纠正后的调用位置，以及三次明确 `read_material(material_id=...)` 的提示。

| 工程事件反例／正例 | 实际结果 |
| --- | --- |
| 只有 `mcpServerStatus/list` 工具清单，无真实调用 | REJECT：三个材料及实际平台读取均缺失。 |
| 只有 Agent “已读”的自然语言自述 | REJECT：不以自述作为读取证据。 |
| 缺 `frozen-questions` 的成功调用 | REJECT：准确指出该材料缺失。 |
| 缺 `target` 的成功调用 | REJECT：准确指出该材料缺失。 |
| `frozen-questions` 的调用终态为 failed | REJECT：失败调用不计成功读取。 |
| 只有该材料 `item/started`，无成功 `item/completed` | REJECT：未完成调用不计成功读取。 |
| 三材料均成功，但没有实际平台调用 | REJECT：`actual_platform_read` 缺失。 |
| 三材料均成功，但平台调用 failed | REJECT：失败平台调用不计成功读取。 |
| 用其他 material_id 代替 `target` | REJECT：准确指出 target 缺失。 |
| 三个指定材料及平台调用全部成功完成 | PASS。 |
| 平台第一次失败、随后实际成功重试 | PASS：可恢复失败不永久拒绝当前目标。 |

共 9 个拒绝反例、2 个成功／恢复正例通过。静态核对显示守卫调用 2 处，分别在正常报告处理与原上下文纠正之后，
均先于 `public-feedback.json` 写入；失败返回 `ResultContractError`，首次错误有 `recoverable=true` 记录和明确工具补读反馈。
不因新的守卫把报告覆盖校验当作已完成实际读取的替代品。

当前脚本检查命令：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff check modeling_team/v5/scripts/acceptance_case.py
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff format --check modeling_team/v5/scripts/acceptance_case.py
```

首次结果：Ruff check PASS；format check 退出 1，1 个文件待格式化（错误构造换行及提示字符串引号）。
已反馈主 Agent，测试 Agent 未改源码；只等待该格式项补查，不重复未变的全回归。

边界：本轮证明当前成功工具事件的识别与缺失反馈，不证明所读内容的语义判断正确，
也不把主任务正在进行的真实评价升级为 PASS。历史评价结果是否可用，仍须依据其实际读取及目标绑定证据单独判定。

#### 第 3 轮补查收口

2026-10-28 08:54 UTC 起，主 Agent 完成格式整理后，独立复查 `acceptance_case.py` 和仅窄修收尾路径的
`platform_case.py`。两文件 Ruff check／format check 均 PASS：

```text
All checks passed!
2 files already formatted
```

原格式失败已 FIXED，11 个读取守卫正反例及第 2 轮未变的回归继续复用，不重复运行 47 项测试。
核对收尾代码与真实 REST 路由，确认撤销调用为 `POST /api/api-keys/{id}:revoke`，且以返回的
`revoked_at` 确认撤销；cleanup 从已保存结果及 Session completion 建立终态上下文后，复用原
`PlatformScope.cleanup()`，没有另写资源删除／恢复框架。

只读核对 5 个自有 scope 的公共 `cleanup.json` 元数据并断言：

| 证据范围 | 实际结果 |
| --- | --- |
| `platform-normal-001`、`platform-checkpoint-001`、`platform-not-written-001`、`platform-response-001` | 4 个均 `retained-pending-acceptance`。 |
| `platform-partial-001` | `failed-written-retained`，保留部分写入，不冒称应用成功。 |
| 全部 5 个 scope | `sessions_terminal=true`、`no_in_flight_attempts=true`、`protocol_key_revoked=true`、`admin_key_revoked=true`、`aggregate_keys_non_active=true`；各 project key 均 `non_active=true`。 |
| 正常 scope 的 `acceptance-key-revocation.json` | 独立读取 key 的 `revoked=true`。 |

公共原件路径为 `workspaces/v5-codex-p0/platform-normal-001/cleanup.json`，其余四个 scope 为
各自 `platform/cleanup.json`；本轮未读取私有凭据文件，未请求平台接口或修改这些原件。
以上是已保留技术回执的独立核对，不外推为独立语义通过，也不把 retained-pending-acceptance 当作业务接受。

**本轮机械合同测试最终 PASS。** 当前源码身份：

| 文件 | SHA-256 |
| --- | --- |
| `acceptance_case.py` | `66793a092888a96f1e5323f9f77b741474c6b37644c56c0f52f1675e78a374e6` |
| `platform_case.py` | `1d1f8e38f97e3d06b8f5566213e2ef395f8a40c27815200054041759c90a8b71` |
