# R4.0-004 独立功能测试计划

## 范围与判定

依据 `docs/requirements/requirements-v4.0.md` R4.0-004 F1—F8、A1—A11，以及 `docs/delivery/designs/2026-10-01-r4-0-004-process-binding-design.md` §8 T1—T8。本 Agent 仅编辑本文件及自有 `/tmp/r4004*` 探针/证据，不修改产品、开发测试、需求或设计，不提交或重启。复用 requirement-delivery 标准交付的复杂功能验证规则，不新增计划评审。

非目标：A12 真实建模、LLM/semantic start、外部业务调用、并行同步、007 版本固定与兼容、011 接口字段映射、008 自动组装。功能 fixture 仅证明合同、存储和读回，不证明真实建模质量；整体语义交付保持 PARTIAL。

## 环境与前置条件

- 基线 HEAD `d04a8bd` 加冻结的 004 指令/reference/测试增量；其他会话 005 文档改动保留。
- 主 Agent 已于 2026-10-01 19:36:19 +08 重启服务，8001/5173 健康。独立探针使用本机真实 PostgreSQL、Oxigraph 和 HTTP API；不重启。
- 自建随机前缀 Project、Ontology、admin/read key、lease、Batch、Graph。key 不输出到日志；finally 删除自有 Project/key/graph/registry 并确认不存在，保留 JSON 技术证据。
- 可复用 003 临时资源/API/清理技术路径，不能复用开发的 candidate 作为独立业务输入。
- read-model limit ≤2000、statement API limit ≤5000。现有接口没有 offset/cursor，只检查 limit/paging 截断并以足量限定全读/export证明全量；同主语同谓词 delete/create 使用两个既有 Batch。

## 稳定用例与执行方案

| 用例 | 条款 | 独立输入、步骤 | 期望与通过标准 |
| --- | --- | --- | --- |
| T1 共享调用 | A1、A2 | 档案核对流程与抽查流程复用核对 Action/输入输出参数；原档案与补录档案同类，多次同名输出，以调用+参数定位 | 共享定义唯一，各调用/值位置独立；全部 inProcess/inScope/invokesAction/输出引用读回，不按名称或类型绑定 |
| T2 值来源 | A3、A4 | 五类来源；原档案编号与反向关系逐段取值；受控等级常量；前序输出及流程输出；输入单位/集合/转换说明；必填未知、可选省略、无输出与仅成功输出 | 目标及方向、来源身份、未知/省略/不适用/无输出/条件均保留；没有实参/凭证/业务行 |
| T3 条件路径 | A5 | 条件转移、明确 default/no-match、优先与互斥/未知选择说明；替代路径回共同后继的条件化绑定；重新排列条目 | 控制流与数据流分别存在；条件/选择说明不丢失、条目顺序不改变图语义；没有伪造同步 |
| T4 循环 | A6、A7 | 集合与前置/后置循环、嵌套 current item；初始及前轮传递；零次/失败未知；循环外集合与明确选择规则 | 作用域/判断/体/出口、初始与迭代结果可读；零次/缺失声明清楚，不复制迭代实例或自动取末次 |
| T5 能力 | A8 | 人工 Action 无 Operation；某调用采用两个 Operation 的局部上下文、顺序与依赖；011 映射未知 | Action 不被能力步骤覆盖；Operation 本体合同可读；没有字段绑定或真实调用 |
| T6 修订 | A9 | 分两 Batch 修改局部绑定，再修改共享参数的声明；保留失效引用未知说明 | 局部修改不改共享定义；共享修订仍可读取而调用不被自动声明兼容；稳定身份不等于兼容 |
| T7 治理 | A10 | 同 reader/同 IRI 写入前不存在 vs 保护后精确读取；保护调用、参数、规则、来源及 fact predicate；比较公开基线与隐藏后 detail/list/relation/statement/export，limit=1 与全量 | 精确 HTTP/JSON 相同；相关边和标量隐藏，无隐藏 IRI/名称/计数；过滤早于 limit/count；可见模型显式未知与截断独立 |
| T8 全链路/修复 | A11 | 独立完整 candidate/receipt/确定性翻译→真实 Batch dry_run/apply_atomic/幂等回放→足量读回/export；错误引用 item/field 反馈，修正继续；非法 Batch不写入；结构正确语义错误对象/调用输出/条件对照 | 全部定义/引用/属性读回；失败写入不变更版本、修正可继续；独立断言能检出错业务含义，平台结构接受不算 bug；无 Evidence/运行实例副作用 |
| T9 实际输入 | F8/A11 | 检查 Task role_sources、TeamRunner 实际 task text/role package 输入与 authoring、v4 role contract | Modeling/Protocol 实际可见方法/词汇/完整示例；neutral/unified 字段保持区别；不靠未加载 reference 宣称接入 |

功能 PASS：T1—T9 均有适用证据，A1—A11 无未解决产品缺陷且清理验证通过；未执行用例记 BLOCKED。A12 不执行/未授权；总体语义状态 PARTIAL。每轮追加实际命令、工作区状态、结果、缺陷与证据；只对失败/缺口进行必要复测。

## 测试轮次

### 第 1 轮：独立候选入口（2026-10-01）

- 基线 `d04a8bd` 加冻结 004 工作区增量，005 并行文档保留；未改产品。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4004_independent_probe.py > /tmp/r4004-independent-round1.log 2>&1`。
- 4 项入口/确定性翻译断言 PASS；编译拒绝探针误用的 `parameter_definition.missing_value_meaning`，正式字段为 `missing_meaning`，值类型应使用 `value`，不是 `scalar`。属于独立 fixture 错误，产品无缺陷；字段按 003 既有合同修正，不改变业务语义或测试方案。
- 尚未创建任何 Project/key/graph，清理验证 PASS。T1—T9 尚未执行完成，功能 BLOCKED（fixture 已修正，继续第 2 轮），A12 未授权/未执行。
- 证据：`/tmp/r4004-independent-round1.log`、`/tmp/r4004-independent-result-r4004-1cfc5c27ef9548f7a4ac4c245b790677.json`。


### 第 2 轮：真实依赖写入分段（2026-10-01）

- 使用同一探针/方案和冻结基线，第 1 轮参数字段已 FIXED；日志 `/tmp/r4004-independent-round2.log`。
- 24 项断言 PASS：独立 candidate/确定性翻译、条目反排 quads 等价、对象错绑/错误调用输出/去掉条件均由独立业务断言检出；引用错误定位 item/semantic.object，修正可继续；写入前精确不存在响应；Class/Property/Entity 三阶段 dry-run/apply_atomic/幂等回放。
- Relation 阶段 149 Items 超过既有每 Batch 100 上限，返回 HTTP 413 `batch_limit_exceeded`，actual=149/limit=100。属于探针未分段错误，无产品缺陷；按既有阶段内顺序拆成 ≤100 Items 的多个 Batch。其他业务输入与断言不变。
- Project/key/Ontology/GraphSet/Registry/Named Graph 清理 PASS，`cleanup: true`。读回/修订/治理仍未完成，功能 BLOCKED，进入第 3 轮；A12 未授权/未执行。
- JSON：`/tmp/r4004-independent-result-r4004-fa12bc2530a24df38a979162e329a248.json`。

### 第 3 轮：完整读回（2026-10-01）

- 第 2 轮 Batch 分段已 FIXED；同一稳定方案，命令仍为同一 Probe，日志 `/tmp/r4004-independent-round3.log`。
- 517 项断言 PASS：完整三阶段定义/Relation 分段 dry-run/apply/幂等回放；所有 Entity 精确注释、Class 可选、149 条关系/标量、共享身份/同名输出/人工动作/Operation 全量治理 export、三种错语义对照和条目反排。
- 探针错误地要求未过滤的 statement-list `limit=1` 返回全量 `visible_count`。既有 read-model 明确此值在 `truncated=true` 时为 fetch window 下界：本例 `{limit:1, returned:1, visible_count:2, has_more:true, truncated:true, complete:false}`。这是测试期望错误，不是产品缺陷；改为验证下界/截断与足量限定全读/export，授权过滤后 fixture 未达上限时再比较完整可见计数，不发明 offset/cursor。
- 审查自有样本并收窄声明：目标对象参数使用既有 `object_reference`，前轮传递说明不伪装 `call_output` 直接来源。业务场景和既定预期不变。
- 尚未执行 T6 修订、T7 治理及 T8 实际失败修正，继续第 4 轮。清理 PASS，`cleanup: true`，无产品缺陷。
- JSON `/tmp/r4004-independent-result-r4004-3a4bc20d7ca8474680497829a045b8ad.json`；A12 未授权/未执行。

### 第 4 轮：最终独立功能验证（2026-10-01，19:36:19 +08 重启后）

- 基线为冻结的 004 工作区增量；执行期间其他会话提交了 005 需求/设计文档（HEAD 由 `d04a8bd` 到 `11f757c02b895b0831c012a32167188e632f2e77`），未修改本次产品/合同输入。主 Agent 补充既有验证：Team full 2031 PASS/1 既有 SKIP/314 subtests PASS；本 Agent 不把开发结果作为独立业务断言。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4004_independent_probe.py > /tmp/r4004-independent-round4.log 2>&1`。
- 结果：**567 项独立断言 PASS**，75 普通 Entity、487 statement；Class 1、Property 45、Entity/Operation 77、Relation 100+49 Items，均通过真实 HTTP Batch dry_run、apply_atomic、幂等回放。Entity 无强制 Class，精确注释逐字段相等，149 条普通关系与声明标量全部读回，足量限定读取与治理 Trig export 证明本次 fixture 全量。
- 第 1/2/3 轮自有字段、Batch 分段、分页计数期望错误均 FIXED，无产品实现修复。非法真实 Batch 的 `target_entity_iri` 非绝对 IRI 被 `invalid_command_payload` 拒绝，定位 `items[0].payload` 及 client_item_id，workspace version 不变；修正引用后按既有不可变 Batch 内容合同使用新 client_batch_id，在同一 Project/BuildSession/目标中 dry_run validated、apply_atomic applied。原始失败留在 JSON，未覆盖。
- 局部绑定分两个 Batch unlink/link，共享 Action/输入/输出参数完整 properties 均不变。随后共享参数 cardinality 改为 collection 可按同一 IRI 读回；调用保留“兼容性未确认/不能称完整”的已披露缺口，共享 Action 未被改写。
- 同 reader/同 IRI 写入前不存在与保护后精确读取的 HTTP/JSON 完全相等。保护调用、参数、规则、来源和 `literalValue` predicate 后：entity-list 75→71、entity-relations 144→126、statement-list 487→450；结果逐行等于公开基线删除所有隐藏引用后的 expected 子图。`limit=1` 各 visible_count=71/126/450，truncated=false、complete=false；返回首项等于其授权可见集合首项，证明过滤先于分页/计数。自定义 scalar、相关边及 export 均无隐藏 IRI；可见 binding 声明不被改成“无约束”或平台推造 unknown。
- 三种结构合法的对象错绑、错误调用输出、去掉条件对照，沿相同翻译/编译路径被独立业务预期检出；平台接受结构不作为产品缺陷或正确业务证明。实际 Task text/role package 可见 authoring method/example，Modeling 与 Protocol 的 neutral/unified 字段区别保留，mounted role/authoring method 一致。
- 无 Evidence、无外部调用、无运行实例/实参/凭证、无新流程平台类型。自有 Project、Ontology、GraphSet、ApiKey、Registry、GraphState/Revision/Named Graph 清理验证 PASS，`cleanup: true`。
- 日志 `/tmp/r4004-independent-round4.log`；JSON `/tmp/r4004-independent-result-r4004-67b29f4a6c144c329070ea8fc23bee52.json`。
- 功能结论 **PASS**，T1—T9/A1—A11 完成；A12 未授权/未执行，整体语义验收保持 **PARTIAL**。

### 第 5 轮：分页实际首行证据补充（2026-10-01，19:51 +08）

- 复用第 4 轮全部功能结论，只补主 Agent 明确要求的 page/full paging、items 数与实际首行证据；不重复开发全套，不改产品。独立 6 Entity/2 Relation/1 自定义 scalar 的微型 fixture 使用真实依赖，无 LLM。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4004_paging_evidence_probe.py > /tmp/r4004-independent-round5-paging.log 2>&1`。
- **26 断言 PASS**。完整公开读取为 entity-list 6、entity-relations 2、statement-list 27；`limit=1` 的未过滤 relation/statement visible_count=2、truncated=true、complete=false，明确是下界，未声称全量。授权过滤后的全量分别 2/1/9，`limit=1` 的 visible_count 分别 2/1/9，truncated=false，所有实际 page_first_item 均等于同一授权 full_first_item，JSON 保留完整 paging、数量及具体首行。
- 全量读取的 requested limit=2000 被既有模板 ceiling 限为 entity 500、relation/statement 1000；本 fixture 与第 4 轮 75/144/487 均低于 ceiling，full paging complete=true，所以确有全量读回证据。没有 offset/cursor，也未从返回行顺序推导流程语义。
- 自有资源清理 PASS，`cleanup: true`。日志 `/tmp/r4004-independent-round5-paging.log`；JSON `/tmp/r4004-independent-result-r4004-513b22953b4548e991cf10616da9d070.json`。

## 最终条款判定

| 条款 | 结论 | 独立证据与边界 |
| --- | --- | --- |
| A1 | PASS | 两流程/重复调用共用 Action 与参数，独立调用和值引用、上下文全部读回 |
| A2 | PASS | 同类 original/sample/补录结果分离；同名输出按 call+parameter 定位；错对象/错调用对照检出 |
| A3 | PASS | 五类来源、目标/方向/单位/集合/转换未知；多段属性正向/反向说明、流程输出全部读回 |
| A4 | PASS | 必填显式未知、可选省略、不适用、none/unknown/omitted 输出、仅成功结果保留，不自动补值 |
| A5 | PASS | 明示控制边/条件/默认/无匹配/选择、两种条件化来源；条目反排 quads 相等，不声明同步等待 |
| A6 | PASS | 集合/pre/post/嵌套当前项、来源/body/exit/inScope 读回；无额外迭代实例 |
| A7 | PASS | 初始/迭代传递、循环外集合与选择规则、零次/缺失/失败未知明确，不默认末项 |
| A8 | PASS | 人工无 Operation 仍有定义/效果，局部多能力上下文/顺序/依赖与 011 映射缺口保留；无外部执行 |
| A9 | PASS | 局部修订不动共享定义；共享参数修订可读且不自动声称兼容，失效/待确认缺口披露；007 版本机制未执行 |
| A10 | PASS | 同主体同 IRI 前后 404/JSON 相等；隐藏端点/谓词边和 scalar/filter/count/export；补充真实 paging 采样 |
| A11 | PASS | 独立候选/确定性翻译、真实 PG/Oxigraph Batch 和读回、非法引用修正安全继续、幂等回放/无写入副作用/实际输入 |
| A12 | NOT EXECUTED | 未授予真实建模/LLM/semantic start；本功能样本不能证明资料忠实度、模型质量或真实语义 E2E |

缺陷：**未发现产品缺陷**。前 3 轮是测试 fixture/调用/期望错误，已保留与修正；不要求需求开发 Agent 修产品或新增复测。

总体：**独立功能 PASS；完整需求语义验收 PARTIAL**。第 5 轮结束停止扩展验证。测试文档外仅写自有 `/tmp/r4004*` 探针/JSON/日志；未重启、未提交、未修改产品/开发测试/其他文档。
