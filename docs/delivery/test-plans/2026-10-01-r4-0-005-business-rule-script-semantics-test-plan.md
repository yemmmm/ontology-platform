# R4.0-005 独立功能测试计划

## 范围与判定

复用主 Agent 指定方案：权威需求 `docs/requirements/requirements-v4.0.md` R4.0-005 F1—F8/A1—A10，以及设计 `docs/delivery/designs/2026-10-01-r4-0-005-business-rule-script-semantics-design.md` §8。按 requirement-delivery 的复杂功能验证规则执行独立功能测试；唯一记录为本文件，探针/原始证据为自有 `/tmp/r4005*`。不修改产品实现或开发 fixture，不重启或提交。

非目标：A11 真实建模/独立语义验收、LLM semantic start、脚本执行、外部业务调用、自动派生物化、007 版本与兼容机制、008 组装、011 字段映射。A3/A4/A9 仅验证身份/冲突内容保留及授权，不宣称真实业务语义裁决或自由文本敏感防护。功能 PASS 不代表整体语义 PASS。

## 环境与前置条件

- 主 Agent 通知实现冻结且服务重启健康后，才运行真实写入；记录当时 HEAD/工作区摘要。
- 复用已验证 003/004 的本地 HTTP/PostgreSQL/Oxigraph、随机 Project/Ontology/key/lease、Batch 分阶段、读模型/export 和 finally 清理路径；独立构造档案移交规则输入，不复制开发 fixture。
- `rule_definition` 为非空对象或 null；类别/输入输出状态沿最终批准枚举；文本字段允许非空字符串或 null/省略，未知与省略不当作无输入/输出。`execution_environment` 是文本，不藏端点 JSON。neutral 仅 create；update 使用既有 unified approved projection/Batch 合同，不发明 neutral update 语法。
- API key 仅内存使用、不打印；read-model 全读足量但不超过既有 ceiling，分页计数按 truncated 下界合同。Project、Ontology、key、GraphSet、Registry、GraphState/Revision/Named Graph 均自有且清理后验证不存在，保留技术证据。

## 稳定用例、步骤与通过标准

| 用例 | 条款 | 独立输入/步骤 | 期望结果 |
| --- | --- | --- | --- |
| T1 类别与输入来源 | A1、A2 | 档案移交资格判断和风险等级推导，关联档案/移交 Action/流程；两个流程共用规则和参数，分别流程输入/调用输出；其余属性、常量、迭代项来源显式引用 | 两类规则与范围/输入条件输出完整读回；五种 sourceKind/目标/来源/属性方向/调用/作用域均保留；不复制运行实例 |
| T2 身份与已知冲突 | A3、A4 | 原档案与补录档案金额来源独立；同名不同范围规则；保留脚本 >= 与说明 > 的已披露 conflicting_meanings | 普通关系身份可解析，脚本/语言/说明/冲突声明共同保留；平台不猜测正确对象或自动裁决阈值 |
| T3 缺失与输出范围 | A5、A6 | unknown/not_applicable/empty/none/error/rejected 各项说明；推导既有档案风险，另显式提交稳定风险概念定义；unknown/null/省略声明 | 状态不互转或补值；既有目标/定义键/范围可读；只写提交定义，不执行脚本或自动物化结果 |
| T4 变更与分层 | A7、A8 | 更新脚本+共同变更说明、保留相应调用重审未知；表明 Shape/OWL/平台 Rule Run/外部判断边界的普通定义 | 同一身份字段更新可读，引用仍存在而不自动声称兼容；无新增平台 Rule Run/脚本执行副作用 |
| T5 创建/更新全链路 | A10 | 独立 neutral candidate/receipt/确定性 Protocol 创建→真实 Batch dry-run/apply→exact/list/detail/export；unified approved projection 更新→同样真实链路；清除/恢复注解 | 注解及语义/关系逐字段等价；创建和 update 均真实通过 _compile/prepare；部分字段/null/省略不造意义；无新表/专用规则资源 |
| T6 可修复失败 | A10 | 非 entity 注解、未知 definition_ref；真实 Batch 非法注解类型/枚举/空文本/未知注解字段/未知 payload 字段/非法引用；修正后同一 BuildSession/目标继续 | item/字段/关系反馈可定位；失败不写且版本不变；修正新 immutable client_batch_id 可 dry-run/apply；错误/修复证据均保留 |
| T7 授权与分页 | A9 | 同 reader/同 IRI 写前不存在 vs 受保护后精确读取；保护规则正文资源、输入关系 predicate、输出定义；比较 list/detail/relations/statements/export/page | HTTP/JSON 不可区分；宽读等于公开基线的可见子图，隐藏端点/正文/计数不泄露，过滤先于 limit/count；不以缺边表示无规则 |
| T8 实际角色输入与相邻回归 | F7/A10 | TeamRunner actual task text/role_sources/package 加载的规则方法和复用 004 来源说明；003 Action/Parameter 与 004 来源字段创建/读回不丢失 | Modeling/Protocol 实际能取得规则合同，neutral/unified 区别保留；既有相邻字段不扩展、不被规则注解改写 |

功能 PASS：T1—T8/A1—A10 的机械/功能范围均执行通过，无未解决产品缺陷且清理通过。不能执行记 BLOCKED，缺陷记录严重度、复现、预期/实际与原始证据。A11 未授权/未执行，整体语义状态 PARTIAL。每轮追加记录，复测优先上轮失败和相关回归。

## 测试轮次

### 第 1 轮：探针输入构造（2026-10-01，20:12 +08）

- 基线 HEAD `3537d3dfe441f659d96242a7d2bd8dcb9099c122` 加冻结的 005 产品/角色/合同工作区增量；并行 006 设计和交付记录保留。主 Agent 提供 20:11:42 +08 重启 active、8001 health ok、5173 HTTP 200。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4005_independent_probe.py > /tmp/r4005-independent-round1.log 2>&1`。
- 探针准备阶段的三元组误以两个变量解包，报 `ValueError: too many values to unpack (expected 2, got 3)`。测试 fixture 错误，已修正第三个变量；不涉及产品实现。
- 尚未执行任何 candidate/API/数据库写入，Project/key/graph 均未创建，故无资源残留且无清理动作。没有产品缺陷；T1—T8 BLOCKED（探针已修正可执行），A11 未授权/未执行。保留日志 `/tmp/r4005-independent-round1.log`，继续同一方案第 2 轮。


### 第 2 轮：真实创建与首次更新（2026-10-01，20:13 +08）

- 同一冻结产品/角色/合同基线，第 1 轮输入解包错误 FIXED。命令为同一 Probe，输出 `/tmp/r4005-independent-round2.log`。
- 275 独立断言 PASS：完整候选/receipt/确定性 Protocol、非法非实体注解与未知 definition_ref 定位、真实 Batch 各阶段 dry-run/apply/幂等、所有 Entity 声明/规则 list/detail/exact、普通关系和五类 sourceKind/缺失状态、完整 statement/export、JSON `op:ruleDefinition` 等价；独立 unified revision candidate/approved projection 更新脚本/共同变更并保留冲突和引用。
- 随后探针使用 `update_entity.values` 更新标签，被返回 `invalid_command_payload`、`Unknown payload field(s): values`，定位 `items[0].payload`/`omitted-preserves`；这是既有接口调用错误（正确字段为 `label`/`properties`），不是产品缺陷。首轮执行前静态检查未发现此调用错误，已修正探针。
- 清理验证 PASS，`cleanup: true`；自有 Project/Ontology/key/GraphSet/Registry/GraphState/Revision/Named Graph 已不存在。JSON `/tmp/r4005-independent-result-r4005-7f4c4cbe5d5e4738b100518cbae62bc1.json` 保留实际 Batch 错误和全部通过证据。
- T1—T4 的已执行合同检查 PASS；T5 的清除/恢复、T6 真实错误修正、T7 授权和 T8 角色输入尚未完成，总体功能 BLOCKED（修正可继续）；无产品缺陷，A11 未授权/未执行。继续第 3 轮，仅重跑同一 Probe 必要相关链路。


### 第 3 轮：注解更新与非法输入（2026-10-01，20:15 +08）

- 同一冻结产品基线，前轮 update 标签字段错误 FIXED。命令为同一 Probe，日志 `/tmp/r4005-independent-round3.log`；新增同类对象来源交换的机械对照（结构可翻译、交换身份原样保留，不宣称业务正确性）。
- 324 独立断言 PASS：前轮成功范围重现；独立 unified 更新候选、approved projection/丢字段对照、update 注解省略保留/null清除/恢复、非法对象类型/空对象/类别/状态枚举/空文本的 create/update 实际 Batch 拒绝且版本/内容不变。
- 执行非法 execution_environment JSON 用例时，探针嵌套测试键误写为 `secret`，触发既有请求凭证边界 HTTP 422 `secret_in_payload`/`credential_field`，尚未进入目标 annotation 类型校验。这是测试 fixture 选键错误，无真实凭证、无产品缺陷；改为 `output_format`，保持“对象类型应被拒绝”的原测试目的。
- 自有资源清理验证 PASS（`cleanup: true`）；JSON `/tmp/r4005-independent-result-r4005-55502af1500143388aa3d845f28a222b.json` 保留所有已通过原始证据。T6 剩余错误修正、T7 授权、T8 实际角色输入尚未执行，功能 BLOCKED；A11 未授权/未执行。继续同一方案第 4 轮。


### 第 4 轮：错误修正完成与治理首测（2026-10-01）

- 第 3 轮 env 测试键 FIXED；同一冻结产品输入。命令为同一 Probe，日志 `/tmp/r4005-independent-round4.log`。复建完整 fixture 是剩余治理测试的前置条件，没有另跑开发套件或扩大范围。
- **369 断言 PASS**：T1—T6 全部完成，18 项真实 create/update 类型、空对象、枚举、空文本、env JSON、未知注解/未知 payload/目标覆盖反例准确拒绝且 workspace version/规则内容不变；非法 relation 引用失败后在同一 BuildSession/目标中新 immutable Batch dry-run/apply 成功。平台 Rule/RuleRun/Evidence 均没有新增，普通规则没有授予执行权限。
- T7 精确读取四个隐藏资源的 HTTP/JSON 与同 reader/同 IRI 写前不存在完全相等；entity-list 全量 42→39，实际结果逐行等于公开基线删除完整隐藏引用后的可见子图，limit=1 visible_count=39、首行正确，均 PASS。
- 后续“隐藏 IRI 不得作为 JSON 子串出现”断言失败，原因是保护 `...-qualify` 与独立可见同名规则 `...-qualify-other` 存在字符串前缀关系；完整身份授权子图比较已经 PASS。此为测试比较方式错误，尚无产品泄露证据。修正为完整 RDF/JSON IRI 单元等值，另保留正文检测和实际前缀命中值，不将可见同名规则错误隐藏。
- 清理验证 PASS，`cleanup: true`；原始 JSON `/tmp/r4005-independent-result-r4005-d437f809d69c46a7b9698d161adae18c.json` 保留失败及全部已通过证据。T7 其余宽读/export 与 T8 role text 尚未完成，功能 BLOCKED，A11 未授权/未执行。第 5 轮只执行 T7/T8 剩余范围，复用 T1—T6 结果，不重复非法/修订套件。


### 第 5 轮：治理与实际角色输入复测（2026-10-01）

- 并行 006 文档提交 `273bc83` 只改变需求/006 设计，产品/角色/合同输入未变，已有功能证据继续有效。
- 只完成 T7/T8，复用第 4 轮 T1—T6 产品证据；自有独立候选和真实 Batch 创建是剩余授权测试的必要环境前置，不重跑非法注解/完整修订套件。产品输入未变，005 文档与并行 006 设计变动不影响结果。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4005_governance_probe.py > /tmp/r4005-independent-round5-governance.log 2>&1`。
- **41 断言 PASS**。第 4 轮字串比较 FIXED：JSON 完整 IRI 值与 RDF term 检测均确认没有完整受保护 IRI；证据保留可见 `...-qualify-other` 中对隐藏 `...-qualify` 的非完整前缀命中（entity-list 3 处、statement-list 15 处），`exact_hidden_present=false`，不是产品授权缺陷。
- 同 reader/同 IRI 精确不可区分验证 PASS；完整公开→授权计数：entity-list **42→39**，entity-relations **45→15**，statement-list **239→194**。各授权全读逐行等于公开基线的完整 IRI 可见子图，full paging complete=true/truncated=false。limit=1 的 actual visible_count 分别 **39/15/194**，page_first 与 full_first 实际行相同，说明过滤在 limit/count 前；JSON 保存完整 before/after/page 响应与 paging/首行，非仅计数摘要。
- Protected entity-detail 无行；治理 Trig export 中无完整保护 IRI term 或被保护规则脚本文本；宽读不返回该规则说明和脚本。可见 binding properties 不被改写为 none/无约束。该测试不证明自动发现自由文本复制或敏感词。
- 实际 TeamRunner Task role_sources、package 与 mounted authoring/role 的 business_rule_semantics 一致，Modeling/Protocol 都可取得规则方法，neutral/unified 区别保留。按主 Agent 的冻结说明不要求新增独立挂载规则示例；独立完整规则候选覆盖本需求，来源参考继续复用 004。
- 自有 Project/Ontology/GraphSet/两个 ApiKey/四 Named Graph/Registry/GraphState/Revision 全部清理并验证不存在，`cleanup: true`。测试后 8001 health 为 `{status:ok}`；本 Agent 未重启服务。日志 `/tmp/r4005-independent-round5-governance.log`；JSON `/tmp/r4005-independent-result-r4005-99c1b3db0a904dab8403e1ea90b85af8.json`。
- 本轮 T7/T8 **PASS**；结合同一冻结基线第 4 轮 T1—T6，独立功能总评 **PASS**，未发现产品缺陷。四轮测试 fixture/调用/比较问题均已 FIXED，原始轮次与清理证据完整保留。无需需求开发 Agent 修复或追加功能复测。A11 未授权/未执行，整体语义状态仍 **PARTIAL**。

## 最终条款判定

| 条款 | 结论 | 证据范围与限制 |
| --- | --- | --- |
| A1 | PASS（功能） | 判断/约束、推导、同名独立规则；类别/说明/适用对象/Action/流程与输入条件输出身份逐字段读回 |
| A2 | PASS（功能） | 两流程共享资格规则/输入位置，调用/流程输入来源独立；五种 sourceKind、对象属性方向/调用输出/迭代 scope 全保留 |
| A3 | PASS（机械合同） | 原/补录档案金额身份独立，交换来源候选仍结构合法且交换端点原样翻译；没有据业务资料裁决错绑 |
| A4 | PASS（机械合同） | >= 脚本、> 说明及明确 conflicting_meanings/语言/共同变更原样保留；不宣称自动冲突检测 |
| A5 | PASS（功能） | unknown/not_applicable/empty/none/error/rejected、null/省略声明可读，不自动补值或改变状态 |
| A6 | PASS（功能） | 既有对象结果身份与范围、显式高风险概念稳定业务定义可读；只创建提交的 42 Entity，无自动结果物化 |
| A7 | PASS（功能） | unified 更新脚本/共同变更真实 dry-run/apply/读回，原冲突和受影响引用保留；未交付 007 兼容判定 |
| A8 | PASS（分层合同） | Shape/OWL/平台 Rule/外部判断边界声明保持区分；普通业务规则未创建平台 Rule/RuleRun，也未代表 Action 执行。未调用既有推理/校验/规则引擎，不用此样本替代其运行验收 |
| A9 | PASS（授权功能） | exact/detail/list/relation/statement/export 完整 IRI 端点过滤、正文资源隐藏、实际可见计数/首行证据；不证明自动文本敏感性防护 |
| A10 | PASS（功能） | neutral 创建/unified approved projection 更新、真实 payload/_compile/prepare/dry-run/apply/幂等/读回；非法注解/未知字段/覆盖/引用不写且可修正；省略保留/null清除/恢复 |
| A11 | NOT EXECUTED | 未获真实建模/脚本或外部业务执行授权；功能样本不证明资料忠实度、建模质量或语义 E2E |

产品缺陷：**0**。最终功能结论 **PASS**（第 4 轮 T1—T6 + 第 5 轮 T7/T8），真实语义验收 **PARTIAL**。不建议功能修复或新测试轮次。
