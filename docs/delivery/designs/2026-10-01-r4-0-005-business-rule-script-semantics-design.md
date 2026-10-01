# R4.0-005 业务规则分类与脚本语义设计

## 1. 当前基线、状态与范围

- 日期：2026-10-01。
- 权威需求：[R4.0-005 业务规则分类与脚本语义](../../requirements/requirements-v4.0.md#r40-005-业务规则分类与脚本语义)。
- 状态：需求细化与设计已形成；D1、D2 均由用户于 2026-10-01 明确确认。D2 确认本期只表达推导语义，实际生成关系／节点的物化能力保留为未交付能力。未实施、未独立审阅、未做功能测试或真实语义验收；本设计不授予真实建模、外部调用或平台脚本执行授权。
- 查阅基线：当前 `main` 的 `d04a8bd`；工作区在本轮开始时干净。
- 依赖：[R4.0-002 多视角语义组织](../../requirements/requirements-v4.0.md#r40-002-多视角语义组织与共享定义)、[R4.0-003 Action 与参数合同](../../requirements/requirements-v4.0.md#r40-003-可复用业务-action-与外部能力关联)、[R4.0-004 流程绑定设计](2026-10-01-r4-0-004-process-binding-design.md)、R3.0-009 的统一语义图和现有受治理读取。
- 同步约束：沿用 R4.0-012 的追溯停用范围，不加入 Evidence、lineage 或来源摘录字段。规则脚本可以是业务模型内容，但不得借脚本或自然语言复制受限规则正文来绕过既有授权。

本设计解决一个具体问题：对于“工单金额超过 100000 才允许关闭”这样的业务约束，Consumer 应能取得规则是什么、适用于哪个对象或 Action、输入从哪个流程值来、缺少输入时代表什么、输出是判断还是新事实。只保存一段程序文本，或者把一次图推理结果误当成业务动作，都不能回答这些问题。

本期定义业务规则的语义合同及其最小图表达，复用普通实体、谓词、关系和 004 的值来源引用。平台继续保存和受治理读取语义；实际业务数据、业务动作、规则解释或执行由外部 Consumer／业务系统承担。平台现有 Rule、Shape 和 OWL 图推理只按各自合同工作，不因本需求获得新的脚本执行能力。

## 2. 方案取舍

| 方向 | 行为 | 选择与理由 |
| --- | --- | --- |
| 保存脚本并由平台直接运行 | 保存并运行 Python、JavaScript 或其他程序 | 不采用；平台不获取脚本执行权限、凭证或外部副作用。保存脚本本身仍是业务模型内容，可供获准 Consumer 使用 |
| 直接把现有平台 Rule／Shape／OWL 结果当业务规则 | 用图推理、SHACL 或 `semantic_rule_definition` 的运行结果代表业务判断 | 不采用；这些路径分别负责蕴含／分类、结构校验和平台侧派生运行，不等同于外部 Action 的业务条件 |
| 普通语义节点＋声明语言及外部执行约定 | 规则有稳定身份、输入输出和缺失语义；每项脚本声明语言和执行约定，由外部 Consumer 解释／执行；平台按既有普通图路径保存和读取 | 用户确认采用；不需要新增平台执行引擎、专用资源类型或专用查询 |

D1 已确认：脚本可以是声明式语言、Python、JavaScript 或其他已声明语言，不要求全局统一一种语言；每条规则同时声明 Consumer 所需的语言、版本、输入绑定、输出约定、缺失值、失败处理和执行环境。平台只保存和读取脚本，不执行它。现有 Platform DSL、SPARQL CONSTRUCT 及其平台运行结果属于平台内部执行适配，不能静默当成外部业务脚本。

## 3. 术语和语义分层

| 概念 | 本设计含义 | 不代表 |
| --- | --- | --- |
| 业务规则 | 可复用的判断／约束或推导定义，有适用范围、输入、条件和输出含义 | 已发生的业务事实、Action 本身或平台权限 |
| 判断／约束规则 | 根据输入给出满足、拒绝、警告、资格或其他已确认判断；结果通常被外部流程或 Consumer 消费 | SHACL 的结构合规结果或接口是否成功 |
| 推导规则 | 根据输入产生属性、关系、分类或其他已确认的新事实 | OWL 的一般蕴含、一次运行记录或业务单据行 |
| 脚本 | 供约定的 Consumer 理解或执行的规则表达；声明语言、版本和执行约定，并与输入输出合同共同维护 | 平台自动执行权限、平台内任意脚本入口 |
| 自然语言说明 | 面向 Consumer 的业务解释、适用范围、单位、时间和缺失含义 | 可以静默覆盖脚本的第二份定义 |
| 规则输入／输出 | 可引用的业务位置及其值语义；输入来源复用 004 的 `sourceKind`、`fromValue` 等关系 | 运行时参数值、业务行快照、凭证或隐藏 IRI |
| 生成节点 | 由推导规则产生的语义资源或结果载体；其身份和落点必须由业务定义确定 | 每次运行都可随意创建的新业务对象 |

一个规则可以关联对象、Action 或流程。关联 Action 只表达“该规则约束或说明该 Action”，不表示规则已经执行 Action；流程调用位置和实际来源仍由 R4.0-004 表达。

## 4. 责任边界与现有平台能力

| 能力 | 当前合同 | R4.0-005 的处理 |
| --- | --- | --- |
| OWL／图推理 | 对本体一致性、类型分类、实现和蕴含产生 reasoning result | 可作为规则输入（须明确引用当前 reasoning result），不把推理结果当业务判断或动作 |
| SHACL Shape | 数据类型、基数、必填、枚举和结构指导 | 可约束规则资源结构，不能表达所有业务条件，也不替代脚本／说明一致性 |
| `semantic_rule_definition` 与 Rule Run | 现有 `sparql_construct`、`platform_dsl`、`workflow_state_machine` 的平台侧版本化运行记录，结果写入独立 `rule-result` 图 | 作为现有平台运行能力的边界参考；不得把其 operational body、run ID 或结果图自动当成 R4.0-005 的外部业务规则合同 |
| R4.0-003 | Action、参数、前置条件、效果及 Operation 关联 | 005 提供可复用规则及其输入输出，规则可以被 Action 条件／效果引用；不复制 Action 参数或接口字段 |
| R4.0-004 | 流程调用、对象位置、参数绑定、分支／循环及 `sourceKind` | 005 消费 004 的值引用；不新增一套规则专用来源语法 |
| R4.0-007 | 共享定义修订、版本兼容和引用重审 | 005 提供脚本、说明、输入输出和适用范围的共同变更内容；不自动声称共享规则变更兼容 |
| R4.0-008／009 | 跨视角召回及后续真实建模、独立语义验收 | 本期提供可治理读回和验收场景，不增加领域专用查询或运行额度 |

### 4.1 业务规则与平台 Rule 的明确区别

例：规则“已验收且金额不低于 100000 的工单才可关闭”是业务规则。它应说明适用的工单、验收状态和金额输入、条件、缺失含义及判断输出，并可被关闭 Action 或流程引用。现有 SHACL 可以检查金额属性是否为 decimal、某字段是否必填；OWL 可以推导类别关系；平台 DSL 或 SPARQL CONSTRUCT 可以在获准图集上产生一个 `rule-result`。三者都不能仅凭运行结果证明外部系统已经关闭工单，也不能替业务方决定金额为空时是“不满足”“未知”还是“不适用”。

## 5. 最小语义表达

### 5.1 规则定义节点

规则使用普通 `entity`，在 `semantic_definition` 中声明 `semantic_role=rule`、业务含义和适用范围。未来实施可以在现有 Action／Parameter 注解模式上增加一个受合同约束的 `rule_definition` 注解；本轮不修改该代码或合同。该注解的最小语义字段如下，字段名是实施交接建议：

| 字段 | 含义 |
| --- | --- |
| `kind` | `judgment_constraint` 或 `derivation`；转换是推导规则的明确输出目的，不另造第三个顶层规则类别 |
| `script_language` | 该规则使用的声明式语言、Python、JavaScript 或其他已确认语言；每条规则自行声明，不要求全局统一 |
| `script_version` | 该语言／脚本约定的版本；不以版本号单独证明业务语义一致 |
| `script_source` | 供获准 Consumer 理解或执行的脚本文本；平台保存读取，不执行 |
| `execution_environment` | 外部 Consumer 所需运行环境、输入绑定、输出形式、缺失／失败处理及副作用约定；不得写入凭证 |
| `input_status`／`output_status` | `defined`、`none` 或 `unknown`；沿用 003 的状态语义，省略表示没有信息，不能推断为 none |
| `change_note` | 规则定义变化时对脚本、输入／输出合同、说明、例子或适用范围的共同变更说明；具体兼容和重审沿用 R4.0-007，不新增本条版本机制 |
| `missing_policy` | 对每个输入或输出说明 unknown、not_applicable、empty、rejected／error 等状态如何影响结果；未确认的策略保持未知 |

脚本正文、自然语言说明和结构化输入／输出共同属于一个规则定义，不能分别声明互相独立的当前含义。任何一个改变了条件、单位、时间、空值含义、输出身份或适用范围，都要在该规则定义及 R4.0-007 的变更／重审范围中同步说明。脚本与说明已知冲突时保留二者及 `conflicting_meanings`，规则不得被描述为语义完整或可安全执行；平台不会通过文本猜测器检测或静默选择一方，冲突由 Modeling／独立语义验收依据业务资料判断。

### 5.2 输入、条件和输出关系

规则输入位置使用独立普通实体，保留可区分的身份、方向、值类型、基数、必填／出现条件、单位、枚举及缺失含义。规则输入绑定复用 004 的来源合同：

- `sourceKind` 继续使用 `process_input`、`call_output`、`object_property`、`constant`、`iteration_item`；不为规则增加相似但含义不同的来源枚举。
- 规则输入绑定继续以明确的目标参数和来源值关系表达。示意关系可使用 `toParameter`、`fromValue`、`refersToDefinition`；它们是随业务模型声明的普通谓词，不是新的平台字段。
- 属性来源必须保留对象位置、属性／关系定义和方向；流程输出必须保留调用点与输出参数；循环当前项必须保留所属迭代作用域。规则脚本不得把这些身份压缩成 `工单.金额` 这样的自由文本路径。
- 条件节点可以引用输入、属性、共享定义和 003 的 Action；条件是否互斥、是否穷尽及流程选择方式由 004 或业务资料说明，平台不自动求值。
- 输出位置单独声明其业务结果含义。判断／约束输出可以是满足、拒绝、警告、资格或其他已确认结果；推导输出可以是属性、关系、分类、转换值或业务定义节点。该含义由输出实体的 `semantic_definition` 和普通关系表达；005 不新增参数专属结果字段。未确认的输出保持 `unknown`，不能默认是新对象或覆盖输入。

规则输入／输出定义不保存实际运行参数、数据库行、外部响应、凭证或执行记录。单次调用的真实对象和来源由 004 绑定；接口字段映射由 R4.0-011 负责。

### 5.3 缺失、未知、空值和错误

这些状态必须区分：

| 状态 | 业务含义 | 默认行为 |
| --- | --- | --- |
| `unknown` | 资料、授权结果或当前输入不足以确认值／条件 | 不自动判为 false、空值或通过；结果保留未知 |
| `not_applicable` | 该输入或规则在已声明范围内不适用于当前上下文 | 不把它当作缺失值或普通 false；按规则声明的分支处理 |
| `empty` | 已知集合、字符串或业务值为空 | 只按规则明确的空值语义处理，不替换成 unknown |
| `none` | 规则合同明确声明没有输入或输出 | 这是定义内容，不由查询没有返回边推导 |
| `rejected`／`error` | 外部 Consumer 或业务系统无法完成评估，或输入违反执行约定 | 保留失败状态；不生成成功事实或动作已发生的说明 |

如果规则没有为某状态声明处理方式，Consumer 只能返回未知／未确认，并保留缺口；平台不添加“取首项、空值转零、缺失即通过、缺失即拒绝”等隐含策略。这个约定沿用 003 的 `missing_meaning` 和 004 的条件化输出边界，属于业务语义而非异常处理器。

### 5.4 推导结果的身份、落点和有效范围

D2 已由用户确认：本期只表达“会产生什么语义节点／关系”的合同，不新增自动派生关系／节点物化；实际物化能力作为未交付能力保留。该决定不禁止 Modeling 通过既有候选、Protocol、dry-run／apply 提交已经确认的语义定义，因为那是显式的受治理语义建模，不是脚本运行自动生成。

1. 判断／约束结果是规则评估结果，不创建业务对象；外部 Consumer 或业务系统拥有该结果的运行状态。
2. 推导到既有对象的属性、关系或分类时，输出引用既有对象／定义身份以及明确的有效范围；不把运行 ID 作为业务身份。
3. 只有业务资料给出稳定业务键、创建含义、适用范围和重复／更新规则时，才可以表达一个新的语义定义节点。若没有稳定身份，保留为外部结果或显式未知，不物化为源 Ontology 中的随机节点。
4. 平台已有 Rule Run 若承载推导三元组，继续遵守现有独立 `rule-result` 图和指针合同；本期不把该运行能力宣称为 R4.0-005 的自动生成实现。不得把每次运行的结果图 IRI 传播为业务对象身份或把外部业务记录写入语义图。
5. 规则的推导结果不是 Action 的执行结果。具体业务单据、设备评估记录、运行实例和外部副作用仍在外部系统；本期不交付由脚本自动生成这些内容或新的可查询派生关系／节点。

## 6. 候选、翻译、写入和读取路径

| 环节 | 复用入口 | 005 实施触点与限制 |
| --- | --- | --- |
| Modeling 候选 | [`platform-neutral-candidate-authoring.json`](../../../modeling_team/references/platform-neutral-candidate-authoring.json) 的 entity／predicate／relation／values／`semantic_definition` 和 `definition_ref` | 在当前合同允许的普通 item 上增加经批准的规则注解／关系；不得让 Agent 自行写平台 IRI、Batch、执行参数或证据字段 |
| 角色合同 | [`r4-0-012-modeling-contract.json`](../../../modeling_team/references/r4-0-012-modeling-contract.json) 的共同语义声明及 003 Action／Parameter 合同 | 实施授权后需要补充 `rule_definition` 的字段规则、输入输出状态、逐条语言声明和 Consumer 执行约定；与 004 参数来源引用机械对齐，不改写 004 业务含义 |
| Protocol 翻译 | [`protocol_mechanics.py`](../../../modeling_team/protocol_mechanics.py) 的确定性 item 翻译、`semantic_definition` 复制和关系依赖排序 | 需要有证据时扩展 entity 注解白名单和 payload 复制；不新增 rule 专用翻译器、执行阶段或随机身份 |
| 平台写入 | [`semantic_command_compiler.py`](../../../backend/app/services/semantic_command_compiler.py) 的普通 entity／property／relation 及现有 Shape／Batch | 规则定义和关系走普通语义资源；只修复有证据的字段丢失／引用错误，不新增规则表、运行器或专用资源类型 |
| 平台读取 | [`semantic_read_model.py`](../../../backend/app/services/semantic_read_model.py)、semantic 资源／关系／statement-list 读取 | 受治理结果应能逐步取得规则身份、类别、说明、脚本合同、输入／输出和来源关系；没有授权的脚本正文与关联保持不可见，不用缺边推断无约束 |
| 现有 Rule／Shape／推理 | [`semantic_rule_definition.py`](../../../backend/app/services/semantic_rule_definition.py)、[`semantic_rule_execution.py`](../../../backend/app/services/semantic_rule_execution.py)、[`semantic_reasoning.py`](../../../backend/app/services/semantic_reasoning.py) | 仅复用其边界和运行结果合同。若未来把某规则映射到既有 Platform DSL，必须显式声明它是平台执行适配，仍保留 R4.0-005 的业务语义定义；不把该适配扩展为 Python／JavaScript 等外部脚本执行器 |

`definition_ref` 仅指向当前完整候选中的 item；复用已有定义仍使用原有授权回执／读取绑定，不由规则脚本拼接 IRI。规则自然语言、脚本文本和结构化输入输出在候选中保持同一修订，Protocol 按已有 per-stage dry-run／apply_atomic、回执、恢复和读回合同处理。结构合法、可写入和能被读取不等于规则业务含义正确，也不等于外部执行成功。

### 6.1 字段从 candidate 到读回的具体映射

下表是实现交接合同。`rule_definition` 是未来需要补进活动候选／Protocol／编译器白名单的实体注解；本轮不修改这些并发维护的文件。实现开始前必须以最终活动合同重新核对字段名，但不能把此项缺口留成“有证据再决定”的开放设计。

| 语义内容 | Candidate 表达 | Protocol 阶段 | Entity payload／RDF | 受治理读回 |
| --- | --- | --- | --- | --- |
| 规则身份与共同说明 | `item_kind=entity`；`semantic.entity_id`、`values.label`、现有 `semantic_definition`（`semantic_role=rule`、`business_meaning`、`applicability` 等） | 复用 `_translate_entity`；绑定候选实体 ID，不生成随机业务身份；现有 `semantic_definition` 原样放入 `create_entity`／`update_entity` | 现有实体资源；`op:semanticDefinition` JSON literal 与 label／普通属性同图写入 | `entity-list`／`entity-detail`／精确资源详情的 `detail_fields.semantic_definition`／`properties.semantic_definition` |
| 规则脚本与执行约定 | 规则实体的 `semantic.rule_definition` 注解：`kind`、`script_language`、`script_version`、`script_source`、`execution_environment`、`input_status`、`output_status`、`missing_policy`、`change_note`；输入／输出定义仍由下方参数实体和普通关系承载 | 在 `translate_candidate_to_batches` 的 entity 分支中像 `action_definition`／`parameter_definition` 一样复制到 `create_entity`／`update_entity` payload；实体以外的 item 拒绝该注解并返回 item／字段错误 | `compile_command` 增加 `rule_definition → op:ruleDefinition` 的 JSON literal 投影；只校验对象、字符串、枚举和非空约定，不执行 `script_source`，不写入 Python／JS 运行记录 | `entity-list`／`entity-detail` 的模板增加 `OPTIONAL ?rule_definition`，投影 `detail_fields.rule_definition`；精确资源详情的 `properties.rule_definition` 与写入值等价。普通关系另按关系读取，不把受限端点塞进注解 |
| 规则输入／输出身份 | 输入／输出各为独立普通 `entity`，复用最终 003 合同中已经存在的 `parameter_definition` 字段；规则输出的业务结果含义由输出实体的 `semantic_definition` 和规则普通关系表达。005 不新增或扩展 `parameter_definition` 字段 | 复用最终 003 参数注解白名单和 `definition_ref` 依赖排序；关系端点由当前候选 ID 解析为收据绑定的实体 IRI | 参数实体保留 `op:parameterDefinition` JSON literal；`rule → parameter` 是普通 RDF 关系，不复制参数内容到脚本 JSON | 参数详情和关系／statement-list 逐步读回方向、基数、缺失含义、输出业务含义及规则关联；未返回关系不能推断无输入／无输出 |
| 输入实际来源 | 复用 004 的 `value_reference`／`parameter_binding` 实体和 `sourceKind`：`process_input`、`call_output`、`object_property`、`constant`、`iteration_item`；绑定保留 `toParameter`、`fromValue`、`refersToDefinition` 等普通关系 | 复用 004 的 relation 翻译和 `definition_ref`；不解析 `工单.金额` 等自由文本，不新增规则专用来源枚举 | 关系写入现有语义图；对象属性、调用输出和迭代作用域按普通 RDF 边保存，实际值不写入 | 读取绑定、值来源和端点身份；授权后缺失的端点只表示当前结果不足，不表示没有规则输入 |
| 条件与推导目标 | 条件／结果说明使用有身份的普通实体和普通关系，`usesValue`、`guardedBy`、`producesProperty`、`producesRelation` 等谓词由模型声明 | 按普通 entity／relation 依赖排序；不将条件编译成平台执行计划 | 条件、目标属性／关系和有效范围是普通资源／边；不新增 `rule_node` 或执行表 | 现有资源、关系和 statement-list 读回；Consumer 结合可见脚本和关系解释业务含义 |

当前代码的最小改动触点是明确的：`protocol_mechanics.py` 的 annotation 白名单与 payload 复制、`semantic_command_compiler.py` 的 annotation predicate／验证、`semantic_sparql_templates.py` 的 entity 详情／列表投影，以及对应的 `semantic_read_model.py` 读回字段。`rule_definition` 是本设计确定的实体注解路径，不能把脚本藏在未声明的 `values` JSON 中而绕过合同。上述触点不要求数据库迁移、Rule 执行器、专用规则 API 或新平台资源类型。

## 7. 授权、冲突和失败处理

- 规则实体、脚本、输入／输出关系和结果定义都是普通受治理资源。沿用 R3.0-004 的不可区分读取：无权与不存在的精确读取不泄露规则是否存在，宽查询在分页、计数、排序和 cursor 计算前过滤。
- 规则正文或说明中的阈值、角色和条件可能是敏感业务语义。建模应引用受保护规则，而不是把正文复制到公开流程、Action 或脚本注释中；现有 IRI 过滤不等于文本敏感性分析。
- 脚本与说明冲突、输入／输出引用未解析、共同变更说明不一致和结果身份缺失分别反馈为可定位的规则内容问题；没有不确定写入时不得把可修复反馈升级为 run 永久死亡。
- 如果已经发生不确定写入，沿用现有 Batch／Attempt／回执／恢复路径，保留失败证据；不为 005 增加新的审计、追溯或自动恢复机制。
- 平台只校验字段类型、身份、引用、授权、既有 Shape 和写入完整性。是否忠实表达业务条件、单位、边界、对象身份和结果意义，由 Modeling 和独立语义验收判断；不以平台拒绝结构错误代替语义验收。

## 8. 实施交接与验证意图

本节是未来取得开发授权后的最小交接，不表示已实施。

1. D1、D2 已关闭；实施授权后将结论同步到规则合同、示例、输入输出状态和验收。D1 无需再选择统一语言，D2 的自动物化能力保留为未交付范围。
2. 在活动 Modeling／Protocol 合同中加入规则注解与关系规则，保留 004 的参数来源字段和身份；不得只改提示而让 Protocol 丢掉脚本、说明、语言声明或共同变更内容。
3. 用完整候选验证规则实体、两个输入来源、自然语言和脚本属于同一规则定义、逐条语言／执行环境声明、判断与推导输出，以及受限脚本／说明冲突；修复应定位到 item、字段或关系。
4. 经现有翻译、真实 dry-run／apply 和受治理读回验证字段无丢失；仅在未来明确纳入现有 Platform DSL 时，按其既有运行测试验证适配，不把运行结果写回源图。
5. 功能验证、独立功能验收、后续 R4.0-009 真实建模和独立语义验收分别记录。当前没有任何运行或验收结论。

### 8.1 正常与反例验收

完整场景和反例以[权威需求的 A1—A11](../../requirements/requirements-v4.0.md#r40-005-业务规则分类与脚本语义)为主记录。本设计只保留验证分层，避免把机械检查写成语义裁判：

| 验证组 | 覆盖 | 机械／合同证据 | 独立语义证据 |
| --- | --- | --- | --- |
| 结构与读回 | A1、A2、A5、A8、A10 | 候选字段、实体注解、普通关系、`sourceKind`、状态值经 Protocol、dry-run／apply 后无丢失，现有 Rule／Shape／推理边界不混写 | 业务资料确认类别、来源和缺失含义是否正确 |
| 同类对象与结果落点 | A3、A6 | 目标参数、对象位置、结果关系／节点声明和受治理端点身份可解析 | 独立验收判断原工单／返修工单和生成知识的业务身份、范围与重复语义；D2 结论在此处生效 |
| 脚本与说明 | A4、A7 | 语言、执行环境、脚本、说明和共同变更内容按候选字段保留，冲突字段可定位 | 平台不会从自由文本判断 `>=` 与 `>` 是否冲突；独立验收依据业务资料判定冲突及变更影响，交 007 重审 |
| 授权与敏感语义 | A9 | 精确读取、宽查询过滤、关系端点和计数不泄露受保护资源 | 平台不会自动发现脚本正文中的敏感词；独立审阅确认建模未复制受限规则，Consumer 只按获准结果解释 |
| 真实语义 | A11 | 不以机械写入或功能 PASS 代替结论 | 后续获准场景中独立检查规则分类、阈值／单位、来源、缺失处理、结果身份和有效范围 |

### 8.2 检查要求与完成边界

本轮仅执行文档检查：相对链接存在、Markdown 围栏／表格结构、需求—决策—设计—验收编号对应及 `git diff --check`。不运行后端／前端套件，不重启服务，不创建真实 Project／Ontology，不执行 Rule／Shape／OWL 或真实建模。本轮已关闭 D1、D2；自动派生关系／节点物化仍明确记录为未交付能力。

## 9. 决策收尾

完整决策表见权威需求；本设计当前保留两个用户决策：

- D1：每条规则是否声明自己的脚本语言与 Consumer 执行约定，还是全局统一为一种语言。用户确认采用逐条声明语言、版本、输入／输出、执行环境和失败／副作用约定；平台只保存读取不执行，现有 Platform DSL／SPARQL 运行结果不等同于外部业务脚本（用户确认，2026-10-01）。
- D2：推导输出本期是否自动物化为可查询关系／节点。用户确认本期只表达推导语义，实际自动生成和物化能力保留为未交付；显式受治理建模仍可提交已确认的语义定义，不把运行 ID 当业务身份，不把业务记录写入语义图（用户确认，2026-10-01）。

本设计采用的高把握常规决定是：规则只分判断／约束和推导两类；转换作为推导的明确输出目的；输入输出复用 004 来源合同；unknown、not_applicable、empty、none、error 不互相转换；脚本／说明／输入输出属于同一规则定义并使用共同变更说明；平台 Rule／Shape／OWL 与外部业务规则分层；不新增执行引擎、专用资源类型、领域查询或证据字段。自动派生关系／节点物化明确保留为后续未交付能力。
