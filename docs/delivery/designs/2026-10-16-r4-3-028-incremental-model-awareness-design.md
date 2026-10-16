# R4.3-028 既有模型感知、增量定位与正确提交设计

## 1. 范围与基线

权威需求：[R4.3-028](../../requirements/requirements-v4.3.md#r4-3-028)。D1—D13以需求
决策表为主记录。开始基线`ecffdcb`；已有输入合同代码基线`9e79afa`，首版细化为
`8ac0747`。本轮仅设计及独立设计审阅，不改执行代码／活跃提示，不运行服务、调用
provider、启动建模或验收。工作区无关README及演示材料保持原样。

目标是让新Agent从新增业务资料出发，在较大已有模型中发现相关旧节点／关系，读懂
含义并决定复用、连接、修改或澄清，最终沿原直接写入路径正确应用。首版输入合同仍
保留。设计通过不代表F6—F10已经实现，也不代表真实质量或效率通过。

例子：旧模型有“安装资产”“库存物料”“现场”；新增“保养计划针对在用设备”。
Agent不能得到正确旧节点ID，应自己检索、比较安装资产与库存物料的定义，再复用
安装资产。保养计划与资产的关系必须来自获准新业务，不能从相关性自动生成。

## 2. 已有能力、实际缺口与最小方案

| 位置 | 当前事实 | 本次处理 |
| --- | --- | --- |
| `modeling_team/incremental.py::prepare_incremental`及029 Task模板 | 已生成新Task／scope／Delivery，绑定当前已有Project和显式Ontology集合；模板已要求先读相关旧模型 | 复用[R4.0-029](../../requirements/requirements-v4.0.md)的启动及输入隔离，不新造增量入口 |
| `runner.py::_task_text`、Modeling完整包／最小链包 | 已有直接写入、成功阶段后查询自查及真实scope提示；最小链包有独立Skill | 在这些实际加载路径补写入前发现／比较方法，不能只改完整Skill |
| `get_modeling_context` | 有当前修订、workspace、计数、派生状态和读取入口 | 作状态依据；不是业务概览，不要求先读全部节点 |
| `get_ontology_read_model`及Context Query | 前者支持classes／entities／facts和受限摘要；后者支持业务召回、多表达式、IRI锚点、preview、分页、自适应及相关度排序 | 复用现有工具形成局部概览并定向补读，不加全图目录、业务专用API或新检索引擎 |
| `ModelingReadProxy`／bridge | Host限制获准集合；省略ontology_ids时bridge补主Ontology，显式集合可选择获准多个Ontology；原响应登记到本run并返回platform_ref | 在初次发现中显式传完整获准集合，后续按候选定位；不把省略范围当全项目检索 |
| `ObservedModelBindings.resolve` | 接受本run实际读取／成功回执，核对摘要、scope、revision及当前可读性；Class读模型的id为IRI，现有测试明确不当resource_id | 当前旧Class没有本run创建回执时，需ID的关系端点不能仅靠此读取完成绑定；补§5的程序确定性身份解析 |
| `_direct_ontology_placement` | 单Ontology能放置fields-only创建；多Ontology时candidate可用slice定位，update可用真实target_ref，fields-only create缺少显式归属载体 | 补§6可选placement_ref，指向既有确认拓扑，不猜主Ontology或端点所在Ontology |
| `semantic_mapping_state.mapping_state`及`PlatformScope.apply_mapping_reference_ontologies` | 跨图Mapping还要求owner.reference_ontology_ids；029生成scope当前未透传mapping_reference_direction，Runner原拓扑路径会跳过激活 | 复用原引用配置能力，补§6.1的显式方向透传及仅受影响Mapping的可恢复接通；不把多图可读等同引用就绪 |
| compiler／DirectModelExecutor／平台 | 静态校验、source_map、可信执行字段、单批apply、成功去重和未知写入对账已有 | 沿025复用，不另加读次数门、语义审批、全局事务或执行框架 |

以上来自定向源码和调用点核对，没有GitNexus图覆盖。本轮不改代码；实施上述公共
入口／跨模块变化前再按AGENTS做影响分析，不能用本设计替代代码影响检查。

主要交付是方法及真实采用；身份、归属和跨图Mapping引用配置三个缺口已有代码证据，不能仅用更长提示掩盖。
不复制旧Protocol的“取IRI最后一段当ID”helper，也不恢复Protocol中介。

## 3. 角色责任与发现流程

Coordinator沿原合同确认本轮范围／拓扑及必要业务问题；Modeling承担语义解释和
候选选择。程序只校验可观察的授权、真实引用和执行结果，不判同义、不选方向。
独立Consumer／Judge最后只读验收，不参与选择连接点或修复生产模型。

```mermaid
flowchart LR
  A[获准新增业务] --> B[当前范围与状态]
  B --> C[业务表达召回候选]
  C --> D[定义与关系定向补读]
  D --> E[复用 新建 修改 或澄清]
  E --> F[真实引用与归属绑定]
  F --> G[原编译与原子应用]
  G --> H[业务自查与独立验收]
  D -->|仍有信息缺口| C
```

### 3.1 状态和有限概览

从Runner直接注入的当前scope取得显式Ontology集合，不自行枚举其他Project或扩大
权限。增量首次使用某Ontology前取得其当前context；无关本体无需穷举详情。对多个
获准本体的发现查询显式指定集合，保留返回的逐Ontology修订和索引信息。

以目标业务词检索取得少量主命中和周边预览；必要时对候选所属Ontology读classes／
entities／facts摘要，形成“已知哪些相关概念、哪些定义待读、哪些连接尚不明”的
工作概览。概览可直接写进已有候选说明／handoff note，不强制生成文件或新schema。
不要以读取列表前20条充当全模型概览。只在当前有效scope／revision／权限一致时
复用本run已读内容；跨会话重新取得当前模型依据，不导入旧run目录或私有验收材料。

### 3.2 检索、补读和停止

从新增业务的对象、用途、动作、角色、条件及依赖形成多种表达。例如查询“在用设备”、
“维护对象”和“设备安装位置”，而不只查新名“保养计划”。这些是检索假设，不是
向图中新增的业务事实；没有公开资料支持时不写入猜测的别名。

示意参数（沿当前工具，P／O取Host实际注入值，不可照抄占位值运行）：

```json
{
  "project_id": "<P>",
  "scope_mode": "ontologies",
  "ontology_ids": ["<O1>", "<O2>"],
  "queries": ["在用设备", "维护对象", "设备安装位置"],
  "context_detail": "preview",
  "limit": 5,
  "context_limit": 20
}
```

沿现行hybrid／adaptive／relevance默认；5／20仅为可调整初值，不是硬完成门或每根
独立预算。不默认加resource_types筛选以免漏掉已有关系／映射中的连接依据；针对
清楚的缺口再选当前合法类型。resource_type是检索类型，不能直接当写入resource_kind。

候选IRI来自实际返回。为重要候选再以单IRI查询、`context_detail=full`取得完整定义、
类型和有向关系；跨Ontology同IRI保留各自ontology_id，详情查询只选当前候选所属
Ontology，避免把另一图的说明混为一份。超过当前有界深度时从实际中间IRI继续查，
不能把距离大于一的路径当直接边。preview截断不能证明条件、例外或未知已读全。

匹配和上下文分别沿原match_cursor／context_cursor续页，保持原scope、query和配置；
更换查询词或锚点是新请求，不复用旧cursor。固定读模型没有通用cursor，不给它编造
分页参数；其paging不完整时改走Context Query及定向读取，不宣称已遍历全模型。

停止依据是本次必要依赖已能得到有依据的处理：重要候选已区分、端点与方向有根据、
会改变决定的定义／限定已读；相关截断则继续定向补读或保留具体缺口。未匹配先核对
实际scope、索引／降级及业务表达，有依据后换词、词面检索或读模型定向查。无结果
不是不存在；预算不足也不是语义未知。普通等待／可修正参数错误保持原run继续。

### 3.3 比较和决策

| 结果 | 要有的依据 | 写入行为 |
| --- | --- | --- |
| 复用 | 旧定义的含义、层级、范围、条件符合本轮需要；实际身份明确 | 沿用旧身份与已有合适关系，不为复用生成无意义update |
| 新建并按需连接 | 确有新含义；连接由新资料或有效业务确认支持 | 创建必要节点／关系；无关新概念可独立存在 |
| 修改既有定义 | 新资料确实修订旧含义；相关使用方及兼容性已核对 | 沿既有身份和007的共享变更策略更新；读不全的影响明确披露 |
| 待澄清／未完成 | 多个候选均合理、资料冲突或读取不足 | 区分业务未知与读取／交付缺口；经原渠道澄清，继续安全独立工作 |

同名不合并，异名不自动新建。实例、Class、relation_type和已断言的关系事实分别
判断；概念级连接不能为了适配候选种类而变成实例事实。相似度只影响阅读优先级。
全部复用且无需修改时，沿029无改动交接收口，不调用要求非空changes的工具。
修改共享定义遵守原007，不增加自动克隆、全局影响引擎或平台业务裁判。

## 4. 从读取到已有引用

Modeling通过只读代理得到原平台data及`platform_ref`。其中artifact_path指向本run
真实保留的响应信封，不能拿展示层data中的相对位置直接当保留文件根路径。

| 已读来源 | existing_resource_ref的path示意 |
| --- | --- |
| 固定读模型具体资源 | `/structuredContent/data/items/N` |
| Context Query具体主命中 | `/structuredContent/data/primary_matches/N` |
| 成功apply具体item | 复制resource_bindings中已有完整existing_resource_ref，不按bindings下标拼路径 |

artifact_ref取该次platform_ref.artifact_path；N取实际保留响应中的项，不能用名称、
排名或另一页位置代替。选中preview邻居后优先将其IRI补读为full主命中，再绑定该
实际主命中；statement、derived_reference及邻居摘要不冒充具体Class资源。

程序继续用ObservedModelBindings校验本run观察记录、响应摘要、scope、修订和当前
可读性。字段到来源路径保留在既有source_map／submission快照，原读回执不改写。
业务比较理由与复用／新增／修改决定留在现有note；不创建逐字段追溯表或审批状态机。

## 5. 旧资源身份绑定的最窄补齐

### 5.1 确认的缺口

读模型／普通RDF Context Query返回的id／iri是语义IRI；关系定义的source_class_id／
target_class_id和部分property引用要求真实resource_id。当前resolver明确不会把IRI
当ID，compiler会返回binding_identity_missing；原新建例子的成功回执能提供ID，
但新Team不能依赖旧run回执。因此“检索到已有Class即可沿当前代码写关系”尚不成立。

### 5.2 程序解析原生canonical身份

在`backend/app/services/semantic_export.py::SemanticNamespace`增加一个纯方法
`resource_identifier(kind, iri) -> str | None`（拟定名称），与现有`resource`成对。
它只处理当前Settings的原生资源namespace：精确前缀匹配、非空identifier、严格UTF-8
percent解码，再用**原resource方法**重建，要求与原IRI逐字相等。不是从任意IRI最后
一段取ID，不按UUID正则截取，不宽松归一化外部IRI。非canonical输入返回None。
kind到namespace段的映射复用现有`modeling_handlers.py::CREATE_RESOURCES`的创建资源
表，不从旧Protocol猜测helper复制映射；不维护第二套IRI拼接规则。普通fact／statement
没有这种资源身份，不走此方法。

Runner将当前真实Settings构建的namespace解析能力传给ObservedModelBindings，属于
可信adapter，不由Agent传base_iri。resolver仅在本run已观察的具体resource引用通过
原scope／revision／可读性核对，且当前full读取的RDF类型符合预期kind后，按下列顺序
提供身份：

1. 成功回执中的实际resource_id／resource_iri继续沿025处理。
2. 当前原生resource IRI没有ID时，调用上述确定性逆变换，保留实际ontology／kind／
   revision／IRI和原读取引用，再供compiler读取ID或IRI槽位；内部绑定不篡改读回执。
3. 外部非canonicalIRI仅可用于原来支持IRI的槽位；要求ID的槽位返回可定位
   `binding_identity_missing`及“当前读取不能提供原生执行身份”的说明。保留可读内容，
   不通过复制旧节点、伪造ID或从旧run捞回执绕过。

此解析是平台既有命名规则对真实已读资源的确定性恢复，不赋予新业务含义或权限。
Agent只选真实资源引用，不解码IRI。不能从Agent在fields中直接写的裸IRI走此路径。
当前代码把kind=concept映射成class只能作提示，实际full资源类型须与目标kind一致；
不明／冲突类型可修正反馈，不能靠kind或namespace覆盖模型明确的类型。

新建保养计划会推进revision，旧安装资产的早先普通read随之过期。关系提交前以其
确切IRI重读取得当前引用；新计划仍可用本run成功回执及原resolver的当前可读性检查。
不重复创建计划、不通过循环刷新expected_revision越过业务冲突。

## 6. 多Ontology的fields-only新建归属

增加能力参数`placement_ref`，不改变request版本、六字段change、candidate语义或
compiler／Executor职责。它是**可选的执行范围引用**，格式为`{artifact_ref,path}`，
指向本run已经确认拓扑的一个冻结ontology_plan条目，不直接引用可变工作文件的下标。
Runner在现有拓扑应用成功后，将确认的topology-decision及实际ontology_plan_ids映射
作为一个不可变JSON快照保存在已有`value-semantics/submission-intents/topology-<digest>.json`。
快照含project_id、run_id、topology及ontology_plan_ids，digest绑定全部内容；不更改
Coordinator的原拓扑schema或新建审批台账。引用path形如`/topology/ontology_plan/N`。

通过现有`multi-slice-ontology-plan`通知向Modeling提供每个获准条目的完整placement_ref、
slice_ids及实际Ontology标识；角色不用读取Coordinator私有map或猜path。初始_task_text
仅在已有确认快照时提供同一列表，否则等待原拓扑通知，不以新额外确认阻塞建模准备。
程序接受自己保留并登记的本run快照，拒绝任意Agent自报scope材料及修改后的快照。

拟议能力形状（不是当前已上线schema）：

```text
modeling_submit_model_changes(modeling_id, request, placement_ref=None)
```

- 省略：单Ontology、candidate已有唯一slice归属及target_ref更新／删除照旧；不改变
  既有调用。多Ontology的fields-only create若仍无归属，返回scope_binding_required。
- 提供：Runner从该冻结plan条目及快照内实际绑定得到唯一Ontology，
  为本请求的fields-only create提供归属。Agent不填Ontology ID，不按名称、数组ID或
  关系端点猜放置。跨Ontology端点只是引用，不决定新关系定义的所属图。
- 原candidate归属及target_ref已确定归属时必须与选择一致，冲突返回原change路径的
  可修正scope错误，不覆盖已有绑定。一个请求选一个归属，需要不同归属就保留必要
  多次提交；无逐批翻译／新审批。调用者选择的是原确认计划中的位置，不是再申请拓扑。
- Runner核对引用、当前确认plan摘要、实际scope映射和写授权；当前绑定与快照不一致
  时返回scope_binding_required及现有新通知入口，不能按旧下标绑定新Ontology。
  未获准的同Project图也不能选择。
  单Ontology兼容调用无需新reference。新Ontology创建仍归029及原授权，不由本工具执行。

placement_ref解析后的ontology_placement与原请求一同进入已有submission输入快照／
digest；原request相同但归属不同不得命中同一去重计划。retained_submission_plan的
匹配须含冻结归属和确认plan身份，不能只凭request复用另一图的旧意图。只扩现有
快照、查重匹配和调用参数，不新增持久化表、资源版本或另一套幂等台账。
原意图存在uncertain时仍先对账，不用换placement_ref另起身份绕过写入fence。

### 6.1 跨图Mapping的引用配置（Round 1 High修订）

placement只决定写到哪个Ontology，授权scope只决定可读／可写范围。普通relation_type
的domain／range使用真实Class IRI，当前没有与Mapping相同的reference配置门；TableMapping
等Mapping的目标解析还受owner.reference_ontology_ids限制，不能混用两种合同。

复用已有`PlatformScope.apply_mapping_reference_ontologies`与现有Ontology PATCH，
不降低`semantic_mapping_integrity`校验、不默认把所有可读Ontology加入引用范围。
最小接入为：

1. 当前增量Task明确依赖方向约定：from_slice为依赖方，to_slice为被依赖方；这是
   结构化端点的解释约定，不是程序替业务判断是否存在依赖。`incremental.validate_request`
   新增可选mapping_reference_direction，仅允许既有两个枚举
   `from_slice_depends_on_to_slice`／`to_slice_depends_on_from_slice`。prepare_incremental
   对每个新请求都写入有效方向：显式值原样透传；省略时按当前Task明确约定绑定
   `from_slice_depends_on_to_slice`，即使当时没有Mapping需求也绑定。默认值是准备
   代码的固定合同，不解析objective／自由文本direction；反向约定仅能显式选择。
   Runner通过原Task提示／scope通知向Coordinator及Modeling提供本轮实际约定，
   双方按该约定填依赖端点。PlatformScope.prepare从生成scope取得方向，此后发现
   新依赖不需要改启动文件、同请求快照或增加runtime setter。
2. Coordinator按既有业务／拓扑渠道确认必要cross_slice_dependencies，Modeling只
   报告“新Mapping需要引用某已读定义”的具体依赖。Host按实际plan绑定解析owner与
   dependency，核对均在原授权范围；未确认依赖或不允许的图时向现有协调
   通路返回具体缺口，不能由程序新增业务依赖，也不要求每批重新审批。
3. 首次拓扑应用复用原激活路径。对开门后才发现／确认的Mapping依赖，不能指望
   已被_multi_slice_gate_opened跳过的检查自动重跑：在Runner直接Mapping提交的
   编译成功后、首次apply前复用同一引用准备helper核对当前已确认map／plan和配置。
   仅为本次Mapping涉及的owner处理已确认引用；缺必要确认返回not_written及
   `mapping_reference_scope_required`，包含原change／引用字段位置和所需协调动作。
   已有的安全非Mapping工作继续，原目标可在依赖确认后同run重试，不全run封死。
4. 将原激活helper所需引用集合与owner当前reference_ontology_ids合并，沿现有平台
   更新校验；保留已有引用，避免从新增slice子集计算集合时删掉旧依赖。已有引用的
   保留不是授予本轮读取权限，不向角色暴露不在scope内的旧引用。不得使用本次路径
   做引用缩减或扩大到未经确认的新图；若本轮确需缩减按既有变更规则另行处理。
5. PATCH失败／未知保留真实配置状态，按已有元数据读回核对原目标集合后继续，
   不重放模型apply、不新建run。配置调整导致当前读取／修订失效时，按原revision
   冲突反馈刷新受影响资源并重新核对原意图；执行器仍从真实当前上下文填版本。

本次保证的是按新合同准备的新任务：省略请求选项仍有已绑定方向，新增依赖确认后
可同run继续。历史冻结run或未知Task若缺方向，保留受影响Mapping的配置缺口并
继续其他安全工作；不自动切换其语义约定，也不承诺存在未实现的热修改入口。
历史run是否修复／恢复沿原授权及合同另行处理，不为解决方向而自动追加start。

真实依赖发现、Coordinator必要确认、Host配置动作与原平台Finding分别留在已有
交接／回执，不能把反复invalid_resource_reference归为Agent没读懂业务。当前方法
原来按owner计算完整集合，本次必须用当前配置并集并限定本次受影响owner，保留
其他owner配置；是现有helper的窄适配，不新增引用管理服务或自动恢复框架。

## 7. 实际加载面与实施文件

| 文件／模块 | 必要改动及验证 |
| --- | --- |
| `modeling_team/skills/ontology-modeling/SKILL.md` | 将写入前发现／比较放入方法；替换当前路径中的旧Protocol复用措辞，保留旧模式明确适用边界 |
| 完整Modeling instructions、minimal-chain-modeling instructions及其独立Skill | 同步最短工作指导和原有小链范围；空模型不强制搜索固定次数，旧资产存在时先找再建；通过各package.yaml实际required_skills证明加载 |
| `runner.py::_task_text`及原拓扑通知 | 当前unified角色提示补充写入前发现，沿已有scope注入并提供§6的实际placement引用；Coordinator派单不预给验收连接答案，不替Modeling决定身份 |
| 029增量Task模板及`references/r4-3-025-direct-modeling-contract.json` | 复用已有先读原则，补齐多表达式／定向读取／引用及placement用法，不新造第二份长合同；历史快照不回写 |
| `read_proxy_mcp.py`／`modeling_readonly.py` | 三工具与scope策略复用；仅同步明确范围及真实工具说明，未发现功能缺口不改鉴权、分页或读引擎 |
| `semantic_export.py`、`direct_submission.py`及Runner可信构造 | §5原生身份纯逆变换及真实引用接入；不从Agent裸值推导身份 |
| `capability_mcp.py`、Runner直接入口、`direct_submission.py`原意图快照／重用 | §6可选placement_ref及原确认拓扑绑定、摘要／查重对齐；原六字段与compiler schema继续复用 |
| `incremental.py`、`platform_scope.py`及Runner原引用激活／直接Mapping提交路径 | §6.1显式方向透传、已确认依赖就绪检查、仅受影响owner的引用并集和同run可修正反馈；普通relation_type不加此门 |
| 当前Team tests及backend tests | 复用direct_submission／direct_modeling／wiring、增量启动／加载和namespace测试；见§9，不新建一次性语义裁判 |
| `docs/reference/mcp.md` | 实施时同步新增可选能力参数、读→写引用及确定性身份边界，当前文档不能提前描述为已上线 |

只更新实际选择的当前路径，旧R2.3固定场景不改成通用入口。实施需先检查当时脏文件，
不以设计轮所查源码版本代替实施现场。backend executable变化须跑完整pytest；无UI
变更不要求前端suite。按AGENTS完成服务重启及受影响端点验证；Team新提示只在后续
获准新进程生效，不能给在途生产／验收回写提示。

## 8. 可修正失败与安全边界

| 现象 | 反馈及后续 |
| --- | --- |
| 缺字段、错误层级、不支持语义字段 | 原compiler返回not_written、change／path和修正说明；原目标继续 |
| 无匹配、lexical降级、preview／列表截断 | 报实际读取限制；换业务表达或实际IRI补读，不能声明不存在 |
| 歧义／旧新资料冲突／影响读不全 | 澄清业务含义或保留具体未知／交付缺口；不写当前无依据的内容，其他安全工作继续 |
| 引用越权、类型不符、非canonicalID槽位、placement未确认／冲突 | 在写入前给原引用／change可定位错误；不解码猜测、不改拓扑、不做永久run拒绝 |
| Mapping可读目标不在owner引用配置中 | 依§6.1接原确认依赖／方向及Host引用准备；缺确认返回定位缺口，可同run继续；不靠反复换IRI或放宽平台校验 |
| 当前修订／权限变化 | 原读／写合同重新取得受影响依据；独立冻结验收发现漂移则保留无效／未完成状态 |
| 已应用／索引失败／未知写入 | 信任真实apply；索引问题不重放；uncertain按原Batch／Attempt对账，成功前批保留 |

不增加必须先通过所有检索检查才能提交的程序状态机。平台硬门只保护授权、真实身份、
确定性应用和资源完整性；感知充分性与业务正确性由Modeling及独立验收判断。

## 9. 验证设计与需求对应

### 9.1 文档／受控工程验证

| 需求验收 | 后续验证意图 |
| --- | --- |
| A1—A3 | 复用六字段、合法例子、原失败形状和可修正反馈测试；不将原交付概要当本次新增情况已通过 |
| A4、A10 | 从实际Task／Profile加载完整及最小包，检查角色可见材料、_task_text、三工具目录、scope和模型隔离；有界替身验证调用／引用投影，关键词检查不等于真实采用 |
| A6—A8 | 受控多scope、cursor、preview／full、无匹配／降级和漂移错误传达；纯程序测试不能断言Agent理解正确 |
| A9、§5 | 无旧run／receipt的已有Class full读引用，经原生身份解析后创建关系，真实domain／range指向原IRI；含不同namespace、类型冲突、percent编码、伪造／过期引用反例；非canonicalIRI仍可保留为合法IRI引用，不强制复制 |
| A9、§6 | 两个已有Ontology、fields-only create显式选确认plan；端点可在另一获准图；省略／冲突／未确认返回可修正错误，旧调用兼容；相同请求不同归属不会重放错图 |
| A7／A9、§6.1 | O1的Mapping引用O2旧Class，可读但未配置引用时不误报就绪；原协调确认依赖后沿已有PATCH激活并成功apply。覆盖启动无Mapping且省略选项仍绑定Task默认、之后新发现依赖同run成功、显式反方向、历史缺值准确报告、未授权图、保留既有O3引用／其他owner、配置失败／未知与同run重试；普通relation_type不被误加Mapping门 |
| A5 | 核对原事件、回执、尝试／阶段计数及已有用量字段的归属，不将Batch数当尝试数 |

namespace逆变换测试须验证`resource(kind, resource_identifier(kind, iri)) == iri`，同时
在实际resolver／compiler／平台集成中证明ID槽位未编码整个IRI。只测helper不算接通。
成功、not_written、partial及uncertain按原025保留；不新增不确定写入处理机制。

### 9.2 后续获准真实增量语义验收

沿029准备有真实定义、关系及相关干扰的非空模型，再冻结基线修订／资料／私有判据。
使用现有Task／Profile／生产与Consumer／Judge工具，不建业务专用route或一次性判分器。
记录节点／关系量、图规模与上下文体积、实际读取子集和截断，证明未全文灌入；具体
样本规模实施时取可复用的已验收模型或固定fixture并披露，不由少量节点通过推导大规模。

新Modeling只获新增原文、已获准scope及当前合同，不能得到正确旧节点ID、期待连接
清单或Judge答案。可有正常公开业务问题，但其措辞不能直接提供应复用的技术锚点。
独立验收持有私有的有效连接／复用和旧业务判据，接受等价合法表达，不锁死唯一图形。

最小覆盖：异名同义、同名异义、概念／实例、跨图实际端点、需中间关系才能区分的
候选、首次无匹配或不完整后的补读、真实未知／无关新概念、全部复用无写入及共享
定义修改影响。公开／隐藏和既有最终独立验收边界保持，分母含失败／未执行。

验收读取新旧资源的实际定义、kind／RDF类型、谓词、domain／range或断言方向，核对
实际复用身份与旧基线；节点全部创建但接错、重复或损坏旧含义均不能PASS。最终
验收只读、不修复生产run，修模另受原用户轮次授权。缺授权或缺模型时保留待实测，
不为设计补证启动真实run。

### 9.3 效率

分别记录发现／补读、比较、写入／纠错和语义验证的墙钟、调用和可得用量；同条件
比较含新增检索、schema／初始上下文、缓存和平台故障差异。首次输入正确不等于首次
语义正确，召回命中不等于复用正确，无对照不宣称净收益。沿019和现有事件记录，
不新增观测平台或固定提速门。

## 10. 交接与审阅状态

实施顺序：对齐实际方法／加载面；接通§5旧身份、§6明确归属及§6.1映射引用准备与回归；复用原输入
合同／直接写入；完成受控工程及规定的backend检查／重启；后续按运行授权取得独立
增量语义及效率证据。实施时只处理当前证据指向的最窄缺口，不重建检索或执行链。

独立设计Round 1为REVISE（0 Critical／1 High：跨图Mapping引用准备遗漏）；Round 2
将同一问题收窄为缺方向时的接点未闭合，仍REVISE（0 Critical／1 High）。§6.1明确
新任务准备时总是绑定实际方向后，独立Round 3完整复审**PASS：0 Critical／0 High，
无关键未决假设**。本结论仅为设计通过，新增实现、独立功能及真实增量语义／效率
未验证。审阅输入摘要、三轮结论和状态同步边界见
[独立设计记录](../records/2026-10-16-r4-3-028-design-review-record.md)。
