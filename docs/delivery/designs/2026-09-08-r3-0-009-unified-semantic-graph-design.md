# R3.0-009 统一语义图与共性抽象：功能设计

状态：Round 4 REVISE 的两项 High 已核实、修订并通过 Round 5 专项独立复审 PASS（2026-09-08）；此前评审记录保留。
本设计已于 2026-09-09 实现并通过独立测试 Round 3 PASS（Round 1/2 的 High/Medium 缺陷均已修复并复测；
3 项 Low 记录在案不阻塞机械验收）。S11/B02/B08/F03/F07/F10 与 Q01-Q07 真实语义验收待 R3.0-006 授权，
不因机械 PASS 提前声明完成。

关联需求：`docs/requirements/requirements-v3.0.md` 的 R3.0-009（D1-D9、节点/兼容合同、候选批准合同与
最小验收条件）；基线为 R3.0-002、R3.0-004、R3.0-006、R3.0-007、R3.0-008A、R3.0-008B、R3.0-011。

## 1. 目标与完成边界

本需求把“统一语义图”定义为同一授权 Graph Set 内按稳定 IRI 发现、读取、双向遍历现有语义资源的
产品视图，不是把 Named Graph、Ontology 或 Evidence 物理合并。目标是让基础业务语义可以先于正式
Class 建立，同时保留正式类型、Shape、规则、权限、dry-run/apply 和值物化边界。

本轮设计冻结以下可实施结果：

1. Entity/semantic resource 允许零个或多个显式正式 Class，旧单 Class 输入仍可用；不增加“共性节点”
   平台资源类型。
2. 属性、关系类型和实体创建路径只在确有批准语义时要求 domain/range/Class；业务分类不伪装成正式
   类型或约束。
3. 009 Team 流程有可选择、可校验的候选版本和独立批准绑定；普通用户仍使用既有产品授权、编辑锁和
   确定性写路径，不被强制纳入 Team Coordinator 审批。
4. 现有 EntitiesPage、ClassesPage 和 Agent/MCP 读写合同都能表达无 Class、全量多分类和 IRI 导航；不
   建设新的单一画布。
5. 平台/流程验收、真实语义验收、清理与证据分别判定。本轮不声称其中任一实现或验收已经通过。

### 非目标

- 不新增 `semantic-node`、`commonality` 等资源/存储类别，不批量迁移既有 RDF。
- 不实现自动聚类、抽象评分、默认值传播、通用继承引擎或把“常见/可能”编译成普遍继承。
- 不新增后端审批中心、全平台 Coordinator 门、编排框架、恢复框架、长期版本治理或新画布。
- 不把 PostgreSQL 客户、设备、工单等业务行复制为 RDF 个体；受控值仍受 008A/008B 物化时点约束。
- 不在细化轮运行真实 modeling、apply、生产写入或修改产品代码。

## 2. 已采用的功能决策

下表均已达到用户授权的 80% 推荐门槛；把握是设计判断，不是运行证据。

| 决策 | 本设计采用的合同 | 把握/理由 |
| --- | --- | --- |
| D1 | 复用 Semantic Resource、Entity 与稳定 IRI；不新建共性资源类 | ≥90%，符合 RDF-first 与旧资源兼容边界 |
| D2 | 正式 Class 为 0..n 显式成员；普通分类用具体业务谓词 | ≥90%，避免单 Class 和错误继承 |
| D3 | 解除非必要 Class/domain/range 前置；已提供的约束仍验证 | ≥85%，无 Class 节点及无约束关系必须可表达 |
| D4 | 节点、每条成员/多重分类、每条共性间关系独立批准 | ≥90%，防止节点批准替代关系批准 |
| D5 | 无有价值共性可带理由继续；过期/冲突只阻止受影响写入 | ≥90%，符合按需抽象与可恢复失败规则 |
| D6 | 复用 EntitiesPage/ClassesPage，补最小创建、分类和导航能力 | ≥85%，同时覆盖用户与 Agent，不引入画布 |
| D7 | Graph Set 内按 IRI 跨资源种类读取、遍历、双向召回 | ≥90%，复用现有授权查询和来源边界 |
| D8 | 复用 SHACL 引擎和 Shape 资源，补齐节点/谓词主体 target 的托管写读路径；冲突显式，不自动传播共性属性 | ≥85%，R4 证据纠正“无类 Shape 已有”的假设；不建设新引擎 |
| D9 | 先做机械/平台独立验收，真实质量随 008B 第二段、011、006 取证 | ≥90%，机械 PASS 不等于语义完成 |

## 3. 参与者与路径选择

### 3.1 普通用户/已有产品路径

普通用户创建或编辑资源时继续通过现有产品授权、工作区/编辑锁、确定性命令、dry-run/apply 和版本
检查。无论资源是否启用 009 Team 候选，都不要求先创建 Team run、Coordinator 决定或全平台审批。旧单
Class payload、旧页面链接和已有 Ontology 的语义保持可用。

### 3.2 启用 009 的 Team 路径

复用现有 `modeling_team/profiles/r3-0-002-modeling-team.yaml`，不增加 Profile registry 项、不使用
仅供 formal run 的 `--model-profile`。新增 Task 参数 `unified_semantic_graph: true` 作为唯一选择器，
同时要求现有 `multi_slice_workflow: true`、`staged_modeling_decisions: true`。缺省/false 走旧合同；
非法配置在 validate 阶段返回可定位配置错误，修正配置后可重试，不消费建模授权。

实施时新增 `modeling_team/tasks/r3-0-009-unified-graph-real.yaml`（task_id 同文件主名），从 008B
真实任务复用输入与工具边界，挂载新引用 `modeling_team/references/r3-0-009-unified-graph-contract.json`；
这些是待实现资产，本轮不创建或启动。合同引用分别进入 Modeling/Coordinator/Protocol 的 role_sources
及已有 source allowlist；旧任务继续挂旧引用。contracts.py 扩展封闭参数集合/依赖校验，Runner、
capability 注册/广告、Codex 定向 bind、产物加载和 prompt 条件分支都读取同一 Task 参数，不能各自猜版本。
`validate --profile modeling_team/profiles/r3-0-002-modeling-team.yaml --task <009-task>` 必须可解析；
未来真实运行再沿同一 profile/task 的 run 命令，并满足 006 授权和 011 依赖。

stage3 路径名不变；新版 schema、各产物路径及兼容分派固定在 §9.1。Protocol 在该模式下做确定性
翻译，并在 intent/receipt 中保存候选、批准和实际命令绑定。下文“009 profile”均指此 Task 参数选中的
009 模式，不是新 profile ID 或模型供应商 profile。

这是对现有 `modeling-batch-item-contract.json` 固定阶段的受控增量：平台/API/UI 的“无 Class、零/多 Class
和可选 domain/range”能力是全局兼容增量，普通用户可直接使用；旧 Team profile 仍按自己的旧 payload
合同产生命令。只有 009 profile 的候选 schema、独立批准和 Runner sidecar 需要显式选择；未启用 profile
的 `class -> property/relation type -> entity -> receipt/read bind -> relation -> shape` 编排行为不静默改变。

## 4. 节点、类型和谓词合同

### 4.1 身份与创建

每个节点继续使用既有 Semantic Resource/Entity 身份、稳定 IRI、所属授权范围和名称。最小实体命令为
身份/名称/范围；`class_iri_or_legacy_id` 在新合同中可省略。编译或验证时：

- 省略 Class 是合法的零成员状态；不得生成空 IRI、占位 Class、`"Unclassified"` 业务类或通过
  `owl:NamedIndividual` 冒充正式 Class。
- `owl:NamedIndividual` 仅是实体标记；它不得进入业务 Class 列表、分类筛选或 Shape 的正式类型集合。
- 新增 `class_iris` 数组承载 0..n 个显式正式 Class；旧 scalar 输入归一化为单成员。两者均省略或
  仅传空数组时为零成员；数组去重并按展开后的 IRI 排序，不允许空串或非绝对 IRI。
- add/remove 一个成员是集合增量，不覆盖其他成员；重复成员去重，输入顺序不改变语义内容 digest。
- 既有 ID/IRI 解析、Project/Ontology 归属、授权和幂等性仍生效；新路径不得绕过 Batch 或 apply fence。

### 4.2 正式类型、分类和继承

- 明确批准的正式成员才写/读为 `rdf:type`；明确批准的集合包含才使用 `rdfs:subClassOf`。
- 普通分类、标签、状态或业务分组使用具有业务含义的已有/新获批谓词，不用无意义 `relatedTo` 代替。
- 共性节点描述属性不自动复制到成员；规则、默认值、Shape 或推理只有在明确批准适用范围时生效。
- `all/some/typical/possible` 是关系作用范围，不是自动继承强度；范围不清保留 unknown，不生成普遍
  类型或类型级关系。

### 4.3 属性与关系类型

`create_property` 可以没有批准的 domain，object property 的 Class range 也可省略；datatype property
仍须给出其实际数据类型，明确提供的 object Class 约束继续校验。`create_relation_type`
可以没有 source/target Class，除非调用者明确提供且平台需要验证。提供的 domain/range 仍逐项检查，不能
用普通业务分类节点填入正式约束。无约束关系仍使用稳定关系 IRI、明确谓词和方向。

正式成员的增删复用 `create_relation` / `delete_relation`，谓词为 `rdf:type`，端点必须为实体及有效
正式 Class；不得借此删除内部 NamedIndividual 标记。节点创建内的 `class_iris` 与独立成员命令均受
同一成员批准合同约束；Class 上下位仍走现有 Class 命令，不误写为实体层成员关系。

实体关系命令继续使用绝对 source/relation/target IRI，且关系方向、来源图、证据和断言类型不能因 Class
缺失而丢弃。关系可达只表示图上的关联，不表示继承或规则已执行。

## 5. 009 候选、批准与确定性翻译

### 5.1 候选包

Modeling 先提交平台中立基础图，再提出共性候选。候选项至少含 `candidate_id`、`candidate_revision`、
逻辑切片/共享范围、语义说明、证据引用和显式 unknown；属性、节点、关系使用稳定局部 ID。候选不强制
填写平台 Ontology ID、页面归属或 RDF 词汇选择，也不携带平台新 ID、Batch ID、receipt ID 或 apply 指令。
重复字段、相同字面量或样例共现只能成为候选，不构成事实。

候选协议以 009 profile 的确定性映射表将局部 ID 映射到既有平台 IRI/命令，不得补猜业务含义、谓词、
关系方向、适用范围、Class 或 Shape。无法确定的值保持 unknown 并回传修复点。

### 5.2 独立批准记录

`value-semantics/approvals/approvals.json`（实际由 `modeling_team/staged_decisions.py` 的既有路径常量
解析）继续是审批产物；009 增加版本化决定条目而不是另建审批存储。
每条决定包括：

`decision_id`、`target_kind`（commonality_node/member_relation/commonality_relation）、`target_id`、
`content_revision`/digest、`decision`（`approved|rejected|deferred`）、理由、证据、逻辑切片/共享范围；
共性间关系另含 `scope`（`all|some|typical|possible|unknown`）。

节点、每一条成员/多重分类和每一条共性间关系的决定互相独立；批准节点不能代替批准成员或关系。候选
内容改变只使受影响决定失效，未改变的独立决定可继续复用。批准的实际命令必须引用 target、revision、
content digest 和批准范围，不能将 rejected/deferred/未批准项目混入同一 approved command。

批准语义之外，009 候选中的每一个基础写入对象也必须绑定：实体、属性、普通关系、正式 Class、Shape
以及共性结构都要在 `decision_bindings` 中引用自己的 `candidate_id`、候选 revision/content digest、
证据和实际 `client_item_id`/命令索引。stage3 slot 的批准是候选包的根完整性批准；上面的三类独立决定
是对共性语义的额外批准，不能用其中任一类替代基础对象的内容绑定。这样普通实体属性不会因为没有
“共性决定”而脱离候选版本控制，也不会把 receipt 的存在误当成业务语义批准。

### 5.3 提交绑定与兼容

复用 008B `protocol_staged_submit_modeling_batch`、耐久 intent、receipt、角色写入归属和现有 sidecar
模式。由于平台 `ModelingItemInput` 对额外字段 `extra=forbid`，009 的 `decision_bindings` 保持 Runner
私有 sidecar：按 `client_item_id`/命令索引绑定候选对象、（适用时）批准 ID、版本、候选 digest 和
profile；不转发为新的普通后端 payload 字段。intent 在转发前保存绑定，receipt 在确定响应后保存实际
绑定和结果。普通用户的命令不要求该 sidecar，但仍受平台自己的授权、版本和命令合同约束。

为使绑定可验证，Protocol 在现有 stage3 产物目录提供逐批物化清单：目标 Ontology、候选到已知 IRI
的对应及来源回执、完整 `items` 投影（kind、payload、依赖、证据）。Coordinator 通过同一 approvals
产物确认翻译忠实于当前获批候选；此确认不替代三类独立语义决定。Runner 按既有 canonical JSON/digest
机制把实际提交 items 与获批清单逐项核对，而非只检查 sidecar 中填写的 ID 或 digest 是否存在。
候选、已批准翻译、实际命令必须三者闭合。后端生成身份只能来自正式回执/读取，关系批次在身份可用
后绑定；不猜测未生成 IRI。幂等键、lease 等执行参数不进入业务决定，但沿既有 Batch 合同验证。

旧 `value_traces`、`l3_nodes`、008B stage3/approval schema 和 R2.3 任务继续可读可执行。只有显式选择
009 profile 时才要求 `decision_bindings`；普通用户和旧 Team run 不受新增 Coordinator 条件影响。

### 5.4 无共性与失败恢复

没有值得抽象的生产场景时，Coordinator 写入有证据的“不物化/拒绝”理由即可继续；代表性 fixture 仍须
满足 R009 最低样本。缺字段、引用缺失、批准过期、范围不明、内容 digest 不符只阻止对应不安全提交；
修复后同一 run 重试。确定性批次仍保持原子性；未知写入结果复用现有对账/kill-switch 边界，不新增恢复框架。

## 6. Shape、规则和读模型

### 6.1 Shape/规则适用

**当前缺口**：托管 create/update Shape 只编译 `sh:targetClass`；guidance reader、Shape endpoint 和
class-shape 模板也只按 Class 读取。节点/谓词 target 是 009 必须交付的增量，不是现有可用能力；底层
pySHACL 能执行标准 target 不等于上述入口、权限、存储和投影已打通。

最小 target 合同如下；复用现有 Shape 资源、constraints、编辑命令及 custom shapes graph：

| create_shape / update_shape 目标字段 | RDF target | 选择的对象 |
| --- | --- | --- |
| `target_class_id`（旧合同） | `sh:targetClass` | 正式 Class 的适用成员，旧输入及类读取入口兼容 |
| `target_node_iri`（新增） | `sh:targetNode` | 一个明确获批的稳定节点 IRI，无需 Class |
| `target_subjects_of_iri`（新增） | `sh:targetSubjectsOf` | 当前数据图中实际使用该谓词的主语，不是谓词资源自身或所有节点 |

每次 create/update 恰有一个非空目标字段；多目标需明确拆成现有多个 Shape，不增加组合 target 语法。
新字段必须是绝对 IRI，沿现有范围/权限与候选批准校验；不从名称猜 IRI。update 沿现有完整定义替换
语义，必须携带目标与 constraints，切换目标时清除旧 target，不把旧新目标并集叠加。delete 复用原路径。
暂不增加 `targetObjectsOf`、字面量 target、自动扫描全图生成 Shape 或新的 Shape 管理页面。

这里“谓词级”仅指上述 subjects-of 选择。`sh:path` 决定检查哪个属性，与选择焦点节点的 target 不同；
subjects-of 无法发现完全缺少该谓词的节点，要求检查缺失必填属性时须选明确节点或 Class target。
这些语义采用 [W3C SHACL targets](https://www.w3.org/TR/shacl/#targets)，不自建 target 推理规则。

`entity-shape` 按 entity IRI 查询时，在同一获准 Graph Set 中收集完整正式类集合（排除
`owl:NamedIndividual`）、匹配该节点的 targetNode，以及匹配其实际主语谓词的 targetSubjectsOf。
拓展现有 endpoint/guidance reader，并为 custom Shape 查询增加这两种 target 分支；旧
class-shape-generated/custom 与 class 端点继续保持按类过滤，不冒充通用列表。无 Class 时不执行虚构
class-target 生成；跨 Ontology 不能只读第一个 ontology/custom graph。匹配和投影只使用当前可见图与
资源，保留 shape IRI、target 类型/值、predicate、来源及完整性；隐藏目标不能通过提示或错误泄漏。

多 Class、节点与谓词主体的适用约束按来源汇集，guidance 不得沿旧“custom/后者覆盖”策略丢弃仍生效的
约束；冲突返回可定位 `shape_conflict`，不猜优先级。旧 class-only 入口保持其既有兼容行为。真实
validation/dry-run/apply 路径仍用原引擎、原校验策略和原子性，必须证明新 target 的实际违例能被检测，
不能以表单提示代替校验，也不因本需求另设所有编辑必须执行新一轮验证的流程硬门。

规则只按既有规则标识、授权 scope 和批准的适用范围读取/执行；共性描述可以作为关联证据返回，
但不能自动改写成成员自身的事实。

### 6.2 统一读取合同

现有 read model/context query 扩展为通用资源与关系投影，不增加业务场景专用路由。最小实体投影如下：

```text
节点：iri, label, aliases, class_iris[]；分类为已有关系投影，不新增 category 资源种类
关系：subject, predicate, object, direction；复用 source_graph_iri, assertion_kind, evidence/lineage
分页与范围：复用既有 envelope 的 cursor/has_more/truncated/completeness 及授权 scope 字段
```

`class_iri`/`class_label` 仅为旧客户端的单值兼容投影；多值客户端使用 `class_iris` 与完整成员边。
上面是所需信息的归属，不新建全资源巨型响应或分页协议。兼容归一化规则固定为：若只给旧 scalar，
则它成为单成员；若同时给 scalar 和 `class_iris`，展开旧 ID 后的 scalar 必须在数组中，否则返回
可定位的 `class_membership_conflict`；空数组与非空 scalar 同传也按冲突处理。旧单值
读取投影在多类结果中选择按稳定 IRI 字典序的第一个**可见**正式 Class，并同时返回 `class_iris`、
已有的完整性状态；它不是多类语义真值。无可见正式类时旧标量为 null。分页或截断造成的非全集只
相对于当前授权可见集合计算 `has_more/truncated/complete`；任何隐藏成员的数量、存在性、
分页差异都不得通过 complete 或旧 scalar 投影泄露。

读取和关系导航在同一授权 Graph Set 内按 IRI 支持 entity/class/rule/shape/evidence 等现有资源
角色，支持正向和反向召回，保留 predicate、direction、source graph、asserted/derived、evidence 与
lineage。跨 Ontology 仅在同一 Project 且授权范围允许时返回。未授权资源统一沿现有 `forbidden`/过滤
合同处理，不泄漏名称、数量、类别、关系存在性或分页差异；所有完整性标志都只描述授权可见结果。

关系的限定含义复用获批谓词的 label、`description`（`rdfs:comment`）及现有 Evidence：说明须包含
适用对象、全部/部分/常见/可能及已知条件，可由通用查询读取。谓词本身的名称与含义须体现限定，
例如“通常需要”不能被替换为无条件“需要”；同一谓词不得被用于相互冲突的作用范围。不同范围需要
不同获批谓词，或显式的现有规则表达，不增加关系元模型或只在 Runner JSON 中保存限定含义。
关系类型读模型须返回 label、description、已有 domain/range、来源和 Evidence/lineage；需执行条件
时再引用获批的现有 Rule/Shape，并验证其实际执行语义。只是“常见/可能”的关系不强制伪造可执行
规则，更不推出成员事实。现有表达不能忠实承载时保留 deferred，并反馈缺失能力，不能丢掉限定。
`scope_policy` / `op:scopePolicy` 保持原有 `schema_allowed|entity_only|both` 的使用位置含义，不能
挪作全部/部分量词；任何 `typical/possible/some` 都不得生成子类或无条件成员继承。

### 6.3 受控值与业务行

数据库编码未知的受控值保持 `analyzed_not_materialized`，不能因为节点无 Class 就创建正式值或绕过
008B。候选和 unknown 的未物化表达只在获准 Team run 产物/诊断中读取，不能混入统一平台 Graph Set、
RDF 或普通产品 read model；平台只读取已批准、已物化的语义资源及其现有缺证据/状态表达。RDF 中仍不得
出现 PostgreSQL 客户、设备、工单等业务行个体。

## 7. UI 与 Agent 交付

### 7.1 EntitiesPage

- 新建表单把 Class 改为可选，允许零或多项显式正式 Class；保留旧单选输入的兼容提交。
- 列表、详情、搜索和关系导航显示完整 `class_iris`/分类集合；无类显示“未分类/无正式 Class”状态，
  但不创建同名业务类。
- 从实体导航到分类/正式 Class/相关节点/规则，并支持反向查看成员；分页、受限范围和来源状态可见。
- 复用现有权限、readOnly 和编辑锁；关系创建只走已有命令/授权路径，不以 UI 绕过后端约束。

### 7.2 ClassesPage 与 Agent

ClassesPage 保留正式类拓扑、关系类型和编辑能力，增加从类到完整成员/分类关系的通用导航；不增加单一
画布。Agent 使用同一 read model、IRI 查询、分页和命令/receipt 合同，不获得 UI 没有的隐藏语义能力。

## 8. 错误、验收与发布顺序

至少提供可定位、可修复的类型化结果：`missing_candidate_reference`、`approval_missing`、
`approval_stale`、`approval_content_mismatch`、`relation_scope_ambiguous`、`shape_conflict`、
`forbidden`、`workspace_version_conflict` 和既有 `staged_unreconciled_batch`。错误包含对象/命令、当前
版本、修复动作和是否可同 run 重试；不以“整次 run 永久失败”替代反馈。

实施顺序（R4 补齐，不得只改 compiler）：

1. 同步命令入口白名单、payload 校验及 compiler：零/多 Class、可选 domain/range，以及 §6.1 新 Shape
   target 的 create/update；保留未声明字段拒绝、身份、范围及确定性写入边界。
2. 完成 §9.3 的 entity-list、entity-search、property-list、装饰/过滤/混合召回与身份交接，再接 UI；
   不以向量召回偶然命中代替正常列表/词法搜索。落实五项 T0 处置与旧身份负例。
3. 打通 Shape 写入、目标匹配、entity-shape/custom 查询、guidance 合并和实际 validation；覆盖节点、
   谓词主体与多 Class，旧 class-only 入口回归。此项是必要新增能力，不得列为“仅复用”而跳过。
4. 接入 UI/Agent、009 候选批准及 intent/receipt；确认新字段/目标也进入获批完整投影和旧模式兼容校验。
5. 执行真实存储的写后读、授权、Shape 违例及旧合同机械验收。真实语义验收仍待 008B 第二段、011 与
   006 新授权，独立验收者只读取保留证据，不生产或修复被验收 run。

### 8.1 高风险假设（最多三项）

1. 现有稳定 IRI/RDF 资源可通过增量编译、读取和 UI 投影承载零/多 Class，无需新增资源类型；源码已证明
   当前 create/read/Shape 有强制单类缺口，但跨存储 apply、权限和真实 SHACL 仍待验收。
2. Runner 私有 `decision_bindings` 可复用既有 sidecar/intent/receipt，不改后端 ModelingItem schema 或
   建立全平台审批；现有 008B 结构支持该边界，实际 intent/receipt 回放与旧任务回归仍待验收。
3. 新节点/谓词主体 Shape 可复用当前 pySHACL 引擎；R4 内存探针已证明两种 target 的错误 datatype
   报违例、修正后通过。但托管入口、跨图读取、合并、权限及真实 apply 完整链仍是待实现/待验收能力。

## 9. 源码证据与最小实施附录

以下是设计输入，不是已完成能力：

| 现状 | 路径/位置 | 对本需求的影响 |
| --- | --- | --- |
| entity 编译要求 `class_iri_or_legacy_id`，写 NamedIndividual 与单个 class type | `backend/app/services/semantic_command_compiler.py:1241-1317` | 需改为可选集合；旧 scalar 仍兼容 |
| create_entity 白名单没有 class_iris；create/update Shape 仅含 target_class_id | `backend/app/services/modeling_handlers.py:146`；`backend/app/services/modeling_handlers.py:469` | 与 compiler 同步扩白名单及 typed 校验；不移除 Unknown payload 拒绝 |
| entity-list 强制类型与类身份；entity-search SPARQL 强制类型；property-list 强制 domain | `backend/app/services/semantic_sparql_templates.py:202`；`backend/app/services/semantic_sparql_templates.py:306`；`backend/app/services/semantic_sparql_templates.py:611` | 补 §9.3 非 Class/domain 身份锚、可选关联、过滤及 T0 决策 |
| 列表混合召回四字段 canonical gate 再次要求 Class；UI 实际消费 entity-list | `backend/app/services/semantic_read_model.py:1702`；`backend/app/services/semantic_read_model.py:1791`；`frontend/src/pages/EntitiesPage.tsx:199` | 不能只改 SPARQL；身份必需字段与可选分类拆开，009 交接同步适配 |
| Shape compiler / guidance / endpoint / custom 模板均只支持类 target | `backend/app/services/semantic_command_compiler.py:850`；`backend/app/services/semantic_shape_guidance_reader.py:17`；`backend/app/services/semantic_shape_endpoint_service.py:54`；`backend/app/services/semantic_sparql_templates.py:279` | §6.1 节点与谓词主体 target 为新增全链路工作；generated class Shape 不冒充支持 |
| 原校验服务把完整 data/shapes graph 交给 pySHACL；guidance 摘要不区分目标 | `backend/app/services/semantic_validation.py:114`；`backend/app/services/semantic_validation.py:327` | 复用引擎；新增适用目标的读取不能把全图 guidance 摘要当作节点的约束 |
| relation type 要求两端 class 并写 domain/range | `backend/app/services/semantic_command_compiler.py:396-485` | 全局命令路径需放宽非必要前置；009 profile 只选择候选/批准绑定 |
| `scope_policy` 已有使用位置语义，不能挪为关系量词 | `backend/app/repositories/models.py:37`；`frontend/src/types.ts:59`；`docs/requirements/requirements-v0.4.md:205` | 保持旧字段含义；限定关系使用获批谓词含义、description、Evidence/Rule/Shape |
| property 要求 `class_id`、datatype 或 object class | `backend/app/services/semantic_command_compiler.py:559-640` | domain 前置需区分“已批准约束”和普通谓词 |
| entity shape 只能由 class IRI 组合，entity IRI 尚不能解析 class | `backend/app/services/semantic_read_model.py:568-607` | 无类和多类读取/合并是实现缺口；改动前需重新 impact |
| batch 字段 `extra=forbid`，sidecar 不转发 | `backend/app/api/schemas.py:496-526`；`modeling_team/references/r3-0-008b-staged-decisions-contract.json:223-305` | 批准绑定放 Runner 私有 intent/receipt sidecar |
| Task 参数和 staged 产物均使用封闭字段集 | `modeling_team/contracts.py:86`；`modeling_team/staged_decisions.py:196` | 009 必须有显式参数及 schema 分派，不能直接塞入新字段 |
| 建模页面新建 entity 同时要求 `newClassIri` | `frontend/src/pages/EntitiesPage.tsx:318-349` | UI 必须同步放宽并显示完整集合 |
| Class/关系图是既有视图 | `frontend/src/pages/ClassesPage.tsx:100-326` | 复用页面，补成员/反向导航，不建画布 |

最小命令与读投影合同：

- `ModelingItemInput` 的实际字段保持 `client_item_id`、`command_kind`、`payload`、`depends_on`、
  `evidence_reference_ids`、`evidence`、`rationale`、`competency_question_ids`；批次层保持
  `client_batch_id`、`ontology_id`、`idempotency_key`、`mode`、`expected_workspace_version`、可选
  `lease_token`/兼容 `actor` 和 `items`。平台/API/UI 零/多 Class、可选 domain/range 能力是全局增量，
  旧 scalar 仍兼容；009 profile 只额外选择候选 schema、decision sidecar 和版本绑定，不将 sidecar
  塞进 `ModelingItemInput` 或普通 payload。
- 读投影必须返回完整 class/category/member/relationship 集合的分页状态、IRI、predicate、direction、
  source graph、assertion kind、Evidence/lineage、stale/warnings 和 authorization scope。
- intent 在转发前持久化候选/批准/命令版本绑定；receipt 在确定响应后记录实际命令、版本、结果和绑定。
  任何未知结果沿现有 reconciliation，不以 receipt 缺失推断“未写入”。

stage3 与权限绑定：Modeling 写候选/分析目录，Coordinator 写 unlock/approvals/checklist，Protocol
写 ledger 和专属 `stage3-neutral-graph/materialization-plans/` 子目录，Runner 写 intent/receipt；
新增子目录由 Runner 预建并仅定向赋予 Protocol 写权限，不能依赖原 Modeling-only 的 stage3 bind。
角色只读取 role_sources/allowlist 明确授权的共享候选、stage3、
批准、平台合同和自身输入/输出，不能把整个 run 根目录挂载给所有角色。011 的隐藏问题/答案、tester-only
材料、Runner 私有 intent/receipt 细节、凭据和其他角色私有目录继续隔离。审批只对启用 009 Team profile
生效；普通用户走现有 SemanticAccessResolver、产品授权/编辑锁和确定性命令。跨 Graph Set 的读取仍由
既有权限解析和 forbidden/filter 合同决定，不能用候选/批准证明扩大读取范围。

### 9.1 版本化产物与兼容分派（Round 1 H1/H2/H3 修订）

选择同路径的新 schema，保留旧 schema reader；不迁移旧 run 文件。以下新增合同仅当 Task 参数为
true 时写入，统一引用在新 contract JSON 中发布。所有路径均相对于已有 run 根，ID 沿用安全本地 ID。

| 产物/路径 | 009 schema | 字段与归属 |
| --- | --- | --- |
| `stage3-neutral-graph/neutral-candidate.json` | `r3-0-009-stage3-slot/v1` | 保留 scenario_id/produced_by/approved_by/candidate_artifacts/slot_note；用 candidate_contract 取代 deferred_contract，指向下面候选版本；Modeling 写，Coordinator 在 approvals 中确认 |
| `stage3-neutral-graph/candidates/<candidate_id>-r<revision>.json` | `r3-0-009-unified-graph/v1` | scenario_id/candidate_id/revision/items/explicit_unknowns；items 含稳定 id、kind、业务含义、值/关系端点、证据、逻辑切片/共享范围及未知；Modeling 写，不含猜测的平台身份 |
| `value-semantics/approvals/approvals.json` | `r3-0-009-approvals/v1` | schema_version/scenario_id/maintained_by/entries/decisions/translation_approvals；Coordinator 唯一写者 |
| `stage3-neutral-graph/materialization-plans/<plan_id>-r<revision>.json` | `r3-0-009-materialization-plan/v1` | schema_version/plan_id/revision/projection/projection_digest；Protocol 写，Coordinator 和 Runner 读取 |
| `value-semantics/submission-intents/intent-<ordinal>.json` | `r3-0-009-submission-intent/v1` | 既有 INTENT_FIELDS 加 plan_ref/projection/projection_digest/decision_bindings；Runner 写 |
| `value-semantics/submission-receipts/receipt-<ordinal>.json` | `r3-0-009-submission-receipt/v1` | 既有 RECEIPT_FIELDS 加 plan_ref/projection_digest/decision_bindings；Runner 从保存的 intent 与真实响应生成 |

审批的 `entries` 完整保留旧 conclusion_confirmation/stage3_slot 条目的字段与含义，不混入新种类。
`decisions` 每项固定 decision_id/target_kind/target_id/candidate_id/content_revision/content_digest/
decision/reason/evidence_refs/slice_ids/shared_scope/scope；scope 仅共性间关系必填，其他为 null。
`translation_approvals` 每项固定 plan_ref/projection_digest/approved_by/decision/reason；只接受当前
Coordinator 的 approved 条目放行。内部共性条目的 ID/摘要与对应候选内容、独立批准逐项闭合。

reader/writer 按 Task 模式与 schema 共同分派：旧模式仍只写/验旧 008B v1；009 模式使用上述 schema。
旧 entries 的值确认/阶段批准校验在新版结构中继续执行，新增 decisions 和 translation_approvals
另做闭合校验；`validate_approvals`、stage3 loader、`validate_approval_cross_references`、intent/receipt
读写与对账入口都必须按该规则接入，不能把新对象直接交给旧封闭字段校验。009/旧 schema 模式不匹配
返回可修复错误，不默默降级批准。读取历史证据时按记录 schema 验证；旧 intent/receipt 不会被
补造 009 绑定，旧 run 可按其原合同继续。禁止在同一已有 run 中把选择参数从 false 改为 true 来跳门。

### 9.2 批准投影、摘要及比较时点（Round 1 H2 修订）

`projection` 固定包含 task_id、contract_version（`r3-0-009-unified-graph/v1`）、scenario_id、
session_id、client_batch_id、ontology_id、candidate_id、candidate_revision、candidate_digest、
items、decision_bindings、identity_bindings。items 是实际 ModelingItemInput 全字段投影，包括完整
payload、depends_on、evidence_reference_ids、inline evidence、rationale、competency_question_ids；
按接口默认补齐未传的空数组/null。每条 decision_binding 固定 command_index、client_item_id、
candidate_item_ids、candidate_revision、candidate_content_digests、decision_ids；没有共性决定的基础
项也须绑定候选内容。identity_bindings 每项为 candidate_item_id、resource_iri、receipt_ref，现有资源
用已获准读取的 evidence_ref 代替 receipt_ref；两者恰一，不能伪造未来 IRI。

先展开旧 Class ID，将 class_iris 去重并按 IRI 排序；其他数组保留提交顺序。摘要使用现有标准：
UTF-8、`json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` 后 SHA-256；
不散列自身 digest 字段，不包含 lease、mode、idempotency_key、expected_workspace_version 等执行参数。
候选内容摘要按同一 canonical JSON 规则对当前 item 的完整语义字段计算；批准版本/当前内容皆须匹配。
不同执行参数仍沿现有 Batch/version/lease/幂等合同检查；dry-run 与 apply 可复用同一未改变的语义批准。

比较和保存顺序固定为：

1. 提交前重读当前候选、批准和物化清单，验证角色、版本、引用与独立决定；把真正将要转发的 items
   按上述规则归一化，与批准 projection 比较。sidecar 自报正确摘要不构成通过，实际 payload 变更必须失败。
2. 通过后将完整 projection、sidecar 和摘要保存在新版 durable intent，再原样转发平台 Batch envelope；
   Runner 私有字段不进入后端 payload。008B 的值确认、L3 检查仍在转发前执行，任一失败都不部分写入。
3. 响应确定后 receipt 从已保存 intent 复制 projection_digest/绑定，并保存真实 batch_id/response_digest。
   原有 command digests、value_traces、l3_nodes 和 ledger 对账继续执行；不能把本地 receipt 当作模型质量证明。
4. 响应未知时依照既有幂等键/Batch 查询查明结果，使用已保存 intent 的批准版本对账；不因候选后续变化
   抹掉已发生写入或按新候选重发旧请求。所有新的写请求必须重新经过当前批准比较。新版读取不要求改写
   旧 intent/receipt；缺少新绑定的旧记录只能证明旧合同，不能据此解锁 009 写入。

**批准后固定版本与接收时点（Round 2 H2 修订）**：候选 item 修订和物化清单按 ID/revision 发布后
不可原地改写；修订产生新版本，并重新取得其批准。`translation_approvals` 对同一 plan_ref/digest 的
批准只证明该确定版本，不是对一个可变文件名的永久授权；沿用已有不可变候选发布/内容摘要机制。
Runner 读取并验证批准的同一快照后，以“当前版本校验通过并捕获完整投影”为请求接收时点，之后
durable intent 和 forwarder 必须只使用该内存快照/保存投影，禁止再次从角色可写路径读 payload。
intent 尚未可靠保存则不能转发；保存失败后的重新提交须重新核对当前批准。

此处“修改后批准失效”指旧批准不能用于新内容或之后尚未接收的新请求；不追溯撤回已经接收并冻结
的请求。检查期间无法形成匹配快照、同 revision 内容被覆盖或请求要求新版本却引用旧批准时，返回
approval_stale/content_mismatch，不转发。接收后的新候选/审批修订只影响后续请求；当前请求要么提交
已批准快照，要么因既有 workspace version/lease/apply 条件失败，不能切换成新内容。若较新的批次
先行改变工作区，旧快照仍由现有 expected_workspace_version 拒绝，不新增跨文件或持有网络调用的锁。

### 9.3 零 Class/domain 读侧与 T0 防御处置（R4-H1）

读侧必须覆盖以下实际消费链，保持现有 Graph Set、权限、来源与分页 envelope：

- `entity-list`：以获准 asserted data 中的 NamedIndividual、稳定 entity IRI 和自身 `/vocab/id`
  为身份锚，不以业务 Class 为存在条件；类型及类身份元数据分别可选，身份与类型来自不同图时也可
  关联。class_iris 只表示可见正式类；按实体 IRI 汇总再分页，不能把多类行截断成不完整的单类对象。
- `entity-search` 词法分支与列表 q/hybrid 路径：采用相同合法实体锚；无 class 过滤时可命中零类，
  显式 class 过滤则只匹配该正式成员。过滤使用全部 class_iris，不能只比较旧标量。修正
  `_public_list_semantic_row` 及 canonical_by_iri 的四字段硬条件；向量数据只能排序，身份必须从
  当前受治理 RDF/回执读取补齐，不能靠关闭 canonical gate 放行陈旧或伪造候选。
- `property-list`：以显式 `owl:DatatypeProperty` / `owl:ObjectProperty` 为资源锚，domain 可选，
  不能任意枚举全图谓词。无 class 过滤时返回无 domain 属性及可选 domain 信息；有 class 过滤时
  只返回声明匹配 domain 的属性，不能将无 domain 解释为自动属于全部 Class。同步 caller 过滤/装饰。
- 平台 API、MCP、UI 均走上述投影；009 Protocol 的 canonical read/receipt 身份绑定允许合法零类，
  但每条已有类型边独立核实。旧 R2.3 class-first 任务仍保持自己的必需 Class 合同，不全局放宽
  `modeling_team/r23003_contract.py`；按既有 009 模式在 `modeling_team/protocol_mechanics.py`
  的 read/receipt bind 入口选择新合同，不能把旧四字段验证原样套到零类后再永久终止 run。

原列表注释的 fail-closed 是为避免不完整身份传给 Protocol，不是 Class 必须存在的业务要求。
虽本轮未产生运行死锁，按仓库 T0 五问预先记录该已知防御的收窄决定：

1. **必要不变量**：资源自身身份、真实图成员、已声明类型身份和授权可验证，仍须保护；“每个实体
   至少有一类”在 009 不再成立。无类不能等同于损坏身份。
2. **当前拒绝后果**：mandatory join 静默抹掉合法零类实体；补交相同合法内容也无法自修复。
3. **直接删除的风险**：可能把索引提示、缺身份或损坏类型当作完整回执绑定，因此不直接取消全部校验。
4. **最小处置**：移除 Class/domain 的存在性前置，保留实体身份锚与每条可见已声明关系的有效性。
   可见 Class 缺少自身 ID 等元数据时，节点仍可读，保留已知类型 IRI及可定位的不完整身份提示；
   不伪装成“确定无类”，也不允许需要该类身份的 Protocol 命令绑定通过。隐藏类别不输出此类提示。
5. **已有覆盖**：受治理 Graph Set/保护集负责可见范围；canonical read、版本/lease、批准投影和原子
   dry-run/apply 负责写入身份及一致性。它们不替代读取锚点，所以保留锚点，仅收窄错误的类前置。

推荐把握≥90%；这是达成原零类可见合同的必要改动，不是新增通用身份治理。所有新增反馈均可修复，
不创建占位类，不从 IRI 尾段补造 semantic ID。有关类缺 ID 的旧测试应保留其身份保护目标，新增
“合法零类”和“已声明类元数据不完整”对照，不能仅删除负例。

## 10. 计划评审记录（由主 Agent 填写）

| 项目 | 记录 |
| --- | --- |
| 评审状态 | Round 1/2 REVISE、Round 3 PASS 保留；用户提供 Round 4 REVISE 两项新 High，均 accepted-high；修订后 Round 5 专项复审 PASS |
| H1 | accepted-high：旧 approvals 为封闭 schema，原方案未定义新版与旧 entries 的共存/交叉校验；§9.1 补齐同路径新版 schema、旧 entries 保留及模式分派 |
| H2 | accepted-high：原 sidecar/物化清单缺少可执行字段、摘要及归属，不能证明实际命令一致；§9.1/9.2 冻结完整投影、写入子目录、意图/回执版本与比较顺序 |
| H3 | accepted-high：原“009 profile”没有合法选择面；§3.2 改为复用已注册 Profile，加显式 Task boolean，并列明 loader/广告/引用/bind 传递路径 |
| Round 2 H2 | accepted-high（收窄）：采用不可变批准版本及明确请求接收时点，转发只用已保存快照；不采用跨文件 CAS/持网络调用锁，已有不可变 Batch 和 workspace version 承担接收后的串行完整性 |
| Round 3 复核 | 独立 plan_reviewer 确认批准版本不可变、接收后快照固定、intent 保存失败零转发、后续请求重新校验与 F14 一致；剩余 High 闭合，无待确认项 |
| R4-H1 | accepted-high：列表/词法搜索/属性列表、handler 白名单及混合召回 canonical gate 确有缺口；补 §8/9 端到端改动面与 §9.3 T0 五问，不能只改 compiler |
| R4-H2 | accepted-high：原设计将节点/谓词 Shape 当既有能力；§6.1 明列三个互斥 target 字段及完整写读/校验增量，更新 D8 与实施顺序；不扩建引擎或管理 UI |
| R4 证据边界 | 用户外部评审及主 Agent 源码复核；现有模板在内存 RDF 探针中只返回有类 n1、无 domain 属性为零行；两种新 target 的 pySHACL 内存正反例通过。不是 API/存储/授权/建模验收 |
| Round 5 专项复核 | 独立 plan_reviewer 确认 R4-H1/H2 的实际读写、身份交接、T0 和 Shape 目标链路已明确纳入设计与用例，无剩余关键假设；未扩展审计 context-query 旁路或完整 UI 实现，不表示实现/验收通过 |
| 决策依据 | 三项原始问题及批准快照边界均为功能合同的必要明确化，推荐把握≥85%；不改变业务语义或增加全平台审批/编排机制 |

本文件不记录测试通过、服务健康、真实 modeling、apply 或生产写入结论；对应证据由实现和独立验收阶段
另行补充。
