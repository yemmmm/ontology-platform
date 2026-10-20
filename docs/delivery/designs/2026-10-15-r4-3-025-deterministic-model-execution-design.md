# R4.3-025 模型变更的确定性转换与执行设计

## 1. 范围、例子与基线

权威来源：[R4.3-025](../../requirements/requirements-v4.3.md#r4-3-025)，决策D1—D9以
该条为主记录。本轮授权为细化、设计及独立**设计**验收，不实施代码／活跃提示／合同，
不启动服务、调用provider、修改模型或恢复生产。开始基线为
`fc8be76`（024设计提交）；工作区只有无关未跟踪`docs/presentations/`、`slide-deck/`。

具体例子：候选有“工单”“故障”两个普通定义、`关联故障`对象属性和一条连接关系。
程序按已确认拓扑创建定义／属性，拿真实输出后写关系；若本次只修正工单定义，明确
update并绑定原资源，不能因候选完整重发而把故障再建一次。源外键说明及客户基数未知
原样保留，程序不据此决定一对一、生成SQL或导入工单业务行。

025负责确定性编译、执行上下文、原子调用及结果；[024设计](2026-10-15-r4-3-024-direct-modeling-design.md)
负责实际Modeling能力接入、旧dry-run／翻译门退役、自查及交接。025接口在本文闭合，
024可以机械对齐字段名；身份、原子范围和返回状态没有改变024已验收决定。

## 2. 实现事实与最小改动面

| 文件／符号 | 已有事实 | 后续复用／必要增量 |
| --- | --- | --- |
| `modeling_team/staged_decisions.py::validate_unified_candidate` | 统一图v2封闭外层、七类item、可选三类定义；递归检查definition_ref，value未规定可编译内层 | 保留外层／摘要；增可定位内层规则及本次操作闭合，不把弱校验通过当可执行 |
| `modeling_team/references/r3-0-009-unified-graph-contract.json` | 仍写Protocol手构计划，概要item_kinds只有三类，actual validator已有七类 | 与012／010和实际validator对齐七类并定义value；024同步退役角色／dry proof旧规则 |
| `modeling_team/protocol_mechanics.py::translate_candidate_to_batches` | `_validate_translate_candidate`要求旧platform-neutral-candidate-v3；旧翻译会用namespace拼IRI | 不能直接调用或把统一图转旧格式；只提取无身份猜测的纯字段转换 |
| 同文件`build_unified_resource_binding_receipt`等 | 虽名unified，入口仍走旧格式校验；已有真实read／receipt提取及scope核对 | 复用底层绑定校验，新增对当前统一图／变更载体的适配；不假定同名helper已可用 |
| `modeling_team/runner.py::_handle_execute_approved_plans`、`_handle_staged_submit_modeling_batch` | 真实context、intent／receipt及恢复可复用；旧路径内部先dry-run、查proof／翻译approval | 抽出无旧门的程序调用；不能将旧execute包一层当新能力。公开入口退役归024 |
| `backend/app/services/build_sessions.py::create_session`、`acquire_ontology_lease`、`renew_ontology_lease` | 有实际Session、租约、revision及同Session租约轮换；他人持租拒绝 | 现有生命周期调用填技术参数；不无条件重复acquire／旋转有效token，不抢租约 |
| `backend/app/services/modeling_batches.py::submit` | 授权、revision、compile／Finding、单批atomic、Attempt／恢复已存在 | 仅apply_atomic；补转换错误映射的消费，不重复建执行引擎 |
| `backend/app/services/modeling_handlers.py::ModelingCommandHandlerRegistry` | ALLOWED_FIELDS、command_kinds、outputs_for／prepare是现行字段／输出权威 | 使用真实Settings输出及既有字段规则；不复制IRI规则，不开放任意handler调用 |
| `backend/app/services/semantic_command_compiler.py` | 已有create/update/delete及fact编译；省略／null／空值规则因命令而异 | 原样保持语义；操作矩阵见§4；不统一成JSON Merge Patch |
| `backend/app/services/modeling_batches.py::_attempt_response`、`SemanticRetrievalCoordinator` | 返回workspace before/after、items输出、findings、recovery、retrieval_indexes；索引在写入提交后构建 | 整理结果三态，绑定修订；不由ok／索引成败推导写入或语义成功 |

本轮仅定向源码／call-site检查，没有GitNexus图分析，不宣称图覆盖。实施若更改公共
入口／跨模块调用，依AGENTS做影响分析；无工具时定向引用检查并披露，不重建索引作设计门。

后续代码增量放现有`modeling_team`确定性工具层，纯compiler处理薄信封校验、语义
命令编译及source_map，`DirectModelExecutor`复用Runner现有转发／intent／receipt机制
执行。两者以§3.3的batches／source_map交接，不建通用编译器框架。
平台仅在现有Batch无法提供必要单批引用时补最窄适配，不新增路由／表或任意写入接口。

## 3. 可消费接口与上下文

### 3.1 程序核心接口

对外能力入口为`modeling_submit_model_changes(modeling_id, request或request_ref)`，由Runner核验真实
Modeling身份和范围，读取／冻结candidate与获准绑定，再调用compiler及§3.3的Executor。
Executor不重新理解candidate、target_ref或语义引用。接口目标已明确；并行代码出现同名
入口不等于本轮已验证实际能力目录、调用及绑定集成。
Agent提交完整`request`或其获准不可变`request_ref`；`execution_context`由已认证Runner
构造，不能透传Agent自报值。

2026-10-20 用户确认补齐完整请求引用：原接口只有 candidate_ref，未覆盖 Class 等
fields-only 完整交付的引用输入，导致已正确保存的请求仍由模型再次转录。保留内联，
新增 `request_ref={material_id,path?}`，复用原 HandoffMaterials：由当前 Modeling 发布给
runner，目录必须选择单一文件；不用任意宿主路径，不新增通信边或文件服务。
两种输入恰选一个，未用键省略。Runner 沿现有来源／接收方／当前 run／摘要检查完整
载入一次正文，正文仍是下述原请求对象，不接受工具参数包装。引用错误在写入前返回
准确可恢复反馈；解析后的内容沿同一编译、规范化提交快照、身份去重及原子应用路径，
不把传输方式计入语义提交身份，不更改既有业务字段或不确定写入恢复。原设计审阅
结论保留为当时版本证据，不据它宣称本增量已通过独立审阅或真实降耗验证。

request外层封闭字段：

| 字段 | 规则 |
| --- | --- |
| schema_version | 固定`r4-3-025-model-changes/v1`，版本化的是操作信封，不替代统一图语义版本 |
| candidate_ref | 统一图完整不可变候选的获准run相对引用；纯既有字段修改时可null。加载时实际计算摘要，不信自报摘要 |
| changes | 非空有序数组；每项字段见下表 |

每项封闭字段为`change_id, action, resource_kind, item_id, target_ref, fields`。
所有字段必有；无适用值为null。change_id本请求唯一的中性操作标识，非Batch／平台ID。
action为create／update／delete／set_fact／delete_fact；resource_kind只允许§4矩阵。
item_id指candidate_ref中当前item；fields仅用于未由candidate提供的既有字段变更，
二者恰选其一（delete及delete_fact允许无item_id，只用目标／事实键）。不能在fields
复制完整另一套候选、命令或身份。create当前统一图七类项必须用item_id，不用fields
绕过表示校验；当前统一图没有的Class／Operation等使用既有表示的语义字段形式。
字段值依现有命令语义，禁止command_kind、payload／Batch、depends_on、技术ID及IRI。

- create：target_ref=null；item_id或fields给出完整所需语义。候选被引用并不意味其中
  所有item都创建；未选择item只能作为已绑定依赖或明确未交付项。
- update：target_ref必有，item_id给完整当前语义或fields给明确修改字段；只允许命令
  支持字段，不能把完整对象的缺省值解释为清空。item方式仅转发实际存在字段；create必需字段规则不套用到fields式update。
- delete：target_ref必有，fields=null（delete_fact例外见§4）；不从候选缺项推出删除。
- 所有action的resource_kind必须和item_kind／真实目标种类一致；entity不能偷偷变Class，
  mapping不能当entity。普通entity附action_definition仍是entity，不变Operation。

target_ref沿R4.3-013既有引用机制，指向**已保留获准读取／回执中的一个具体资源条目**；
形式为`{artifact_ref, path}`，path是JSON Pointer。Runner核对该材料可见性、原请求
scope与实际资源种类；schema只认这两个键。不接受裸IRI／显示名称当绑定，不用整个
CQ no_match判断资源不存在。技术引用在信封，不污染中性candidate。

引用只在现有run获准目录解析，复用原越界／symlink及角色可读校验。载体一次加载后
冻结内存快照、计算canonical digest，编译和转发不再读取可变角色路径。该提交在现有
intent旁保留快照／source map即可；不创建新覆盖台账或Evidence模型字段。

### 3.2 可信execution_context

由Runner绑定当前run、真实task_id、已确认Project／Ontology映射及允许操作的scope、
获准来源／业务决定、现有Session与租约凭据、平台adapter、既有资源／item输出绑定。
没有获准Project／Ontology拓扑时返回`scope_binding_required`，不按slice_ids推测。
现有Coordinator对共享语义／拓扑的必要确认继续核对；不是每批命令翻译审批。

缺Session／lease时按现有工具在已授权资源内创建／取得，task_id来自实际加载Task。
有效lease优先复用及按既有规则续租；session_revision／lease_revision／当前model_revision
来自真实服务响应。未授权、他人持租、workspace未就绪、未知写入fence分别返回原错误。
不创建Project／Ontology、不改变保护、不偷取凭据、不自动恢复暂停run。

每次apply前读取实际版本并绑定本次意图：目标或依赖自上次获准read／receipt以来变化，
或prepare后revision冲突，返回可修正冲突及原提交位置，Modeling重新核对原语义意图。
不能为了越过冲突循环更新expected_model_revision。纯技术租约续期不改业务内容，
未知写入对账必须先于任何新请求身份或版本刷新。

### 3.3 Compiler／DirectModelExecutor边界（用户后续确认）

compiler返回`(batches, source_map)`。batches是已按依赖排好的有序数组，每批必含
`ontology_id, items`，另可有`depends_on_batches`和原`batch_index`依赖定位；
ontology_id保留已确认拓扑的真实目标，仅用于scope核对，不授权
任意Ontology写入。compiler不发平台请求、不申请Session／lease、不分配执行身份。

每个item保留以下字段：

| 字段 | Compiler输出／Executor处理 |
| --- | --- |
| client_item_id | 必需；原candidate item identity原样保留，不改成顺序号、UUID或Batch局部重命名；不是平台资源ID |
| change_id | 可选；有显式变更时原样保留，无变更ID时不伪造 |
| resource_kind | 必需；保留已明确资源种类，不能按命令输出改成entity |
| command_kind／payload | 完整语义命令字段；保留缺省／null／空值差异。能力层在交给Executor前把跨批身份引用绑定到真实read／成功output；不猜技术ID或IRI |
| depends_on | 只含同批稳定client_item_id；跨批依赖由source_map的cross_batch_dependencies及批级depends_on_batches表达，Executor据成功状态阻断失败／未知依赖，不负责资源引用解析 |

compiler输出不带session_id、lease_token、expected_model_revision、idempotency_key、
client_batch_id、平台Batch／Attempt或create资源技术ID。scope提供的ontology_id与
candidate的client_item_id是必要交接定位，不属于应移除的执行身份。datatype等语义IRI
原样保留，真实资源引用解析不由compiler猜测。

source_map与batches一同交接，规范结构为：

```text
{str(batch_index): {client_item_id: entry}}
entry.field_map = {payload_pointer: [candidate_or_request_json_pointer, ...]}
```

entry保留原item_id、可选change_id、resource_kind及artifact引用；例如
`field_map["/payload/label"] = ["/items/0/value/label"]`。JSON Pointer按原artifact解析并
保留`~0`／`~1`转义；同名client_item_id在不同批由外层batch_index区分。技术上下文
错误定位change／提交根，不能伪造源字段；Executor不得改写稳定ID或丢弃字段映射。

entry.cross_batch_dependencies沿实际依赖携带depends_on_batch及来源client_item_id；
批级depends_on_batches可直接提供同一依赖。Executor据两者核对前置批真实成功状态，
前置失败、未执行、部分应用或不确定均不放行依赖批。**阻断依赖不等于解析资源引用。**
Executor不解析target_ref、item_ref或IRI，不把cross_batch_dependencies当资源输出。

Runner能力层负责原target_ref的获准读取／真实绑定，以及跨批引用在执行前的解析。
调用execute的本次批次必须已绑定跨批真实输出；还没有该输出时，先执行已有可落地阶段，
保留实际成功回执后准备后续阶段，不把未解析模板塞给Executor或平台。已满足的跨阶段
依赖保留原计划／回执证据；本次执行投影只带当前待执行前置批，不能丢掉失败／未知依赖
来绕过阻断。原batch_index及字段source_map继续对回原提交，已成功阶段不重复创建。
同批合法item_ref仍由现有后端Batch请求内解析，Executor只原样投影，不承担引用解释。

同一candidate item确需多命令时，在不同有序批次保留同一client_item_id，以batch_index
区分映射；没有candidate的fields式操作使用其原change_id作为稳定来源身份。每批
client_item_id唯一；若不能在保留所要求原子性的同时分批，返回原定位的
atomic_dependency_conflict，不偷偷重命名来源ID或拆开原子替换。

Executor接口按用户确认固定为：

```python
DirectModelExecutor(
    scope, run_root, run_id, task_id,
    submit=batch_forwarder, read=scoped_forwarder, observe_result=None,
).execute(batches, source_map)
```

此签名为设计合同，非当前可运行示例。scope、run_root、run_id、task_id来自可信Runner。
scope是§3.2的可信执行上下文，除授权资源集合外，显式承载Runner既有Session／lease
生命周期adapter及当前凭据，不是Agent提交的纯JSON范围声明。submit只作Batch写转发，
read只作受scope约束的读取；创建Session、取得／续租lease使用scope的生命周期adapter，
不把管理写操作塞进read或Batch forwarder，也不新增构造参数／生命周期框架。该adapter
缺失且不能完成必要准备时返回明确能力缺口，不猜凭据或继续写入。Executor取得／填充BuildSession、
lease、revision及执行幂等身份，每批只调用一次apply_atomic，并持久
保留staged intent／receipt／apply Attempt proof。该proof记录真实apply终态，不是dry-run
证明，也不是额外写入许可门。observe_result只观察实际结果，不代替持久回执或语义裁决。

Executor把后端Finding按稳定ID与source_map映射回原item／字段，保留ontology_id及实际
Batch／Attempt；resource_kind、change_id、source_map为Runner sidecar，向封闭的后端
ModelingItemInput只投影其允许字段，不把sidecar塞入payload。§5的去重、结果三态、
索引／修订及恢复合同保持。

## 4. 确定性转换规则

### 4.1 当前统一图value内层（待实施澄清，不回写历史候选）

保留v2外层和八个必需item字段／三个可选定义字段，内部只用现有语义字段，不引入
旧candidate的semantic包裹。当前reference未约束value完整形状，不能承诺所有旧value
都能编译。以下为新提交的规范形；不合规范给原字段错误，不默默丢掉未知键或翻译文本。
旧候选若表达不能唯一转换，作者在新不可变修订中明确所缺字段；不改原件／自动猜意。

| item_kind | value规范与映射 |
| --- | --- |
| entity | value使用create_entity的语义字段label（必需）、aliases、properties（下述中性条目数组）、class_iris／class_iri_or_legacy_id；Class位置用中性definition_ref或获准已有绑定引用，不接受猜测ID。无Class合法，不造Class。item可选三类定义原样转给entity |
| property | value为name（必需）、description及可选class_id／datatype／object_class_id；datatype在字面量属性时必需，datatype与object_class_id互斥。另需明确predicate_kind=fact或relation，它是现有predicate语义选择，仅在转换时消费、不传平台。relation可无形式range/domain。name不是平台property_id |
| relation | value恰为predicate（指property的definition_ref或已有绑定）；relation_endpoints恰为from_item_id／to_item_id，中性字符串指本候选item或同义的definition_ref包装；端点允许当前合同的已有资源引用包装。映射source／predicate／target到create_relation，不按文字判断方向 |
| table_mapping／join_mapping／enum_meaning／metric_definition | value复用现有modeling-batch-item-contract.json对应create_payloads的业务字段，移除资源技术ID；嵌套引用用definition_ref或既有existing_resource_ref。semantic_definition保持；SQL、DSN、source_id／run_id导入变体不接受 |

除relation以外relation_endpoints必须null。现有定义注解字段只在目标handler支持处
转发：匿名relation不接semantic_definition；非法组合给准确反馈，不静默丢弃。property
只支持semantic_definition；action／parameter定义限entity。已有`semantic_definition`、
`mapping_definition`、Action／Parameter对象严格沿012／010／003字段，不新增规则脚本。

business_meaning、item.unknowns、explicit_unknowns不作为payload未知字段塞入，也不能
因平台没有同名字段而消失：普通定义若无semantic_definition，机械组成现有注解对象，
只填business_meaning原文、unknowns原列表（compiler允许部分注解），不按entity／property
资源种类猜semantic_role或applicability。有声明时同名说明冲突返回`semantic_content_conflict`，
未知列表按原顺序去重并集合并，不丢任何已声明未知，其他注解字段原样保留。
relation的含义由已声明predicate和显式端点表达，不以business_meaning文本相等为门；
原说明／未知保留在候选与回执引用中。额外局部含义／条件应由Agent按012建普通节点，
程序不能判断是否需要建节点或把relation文本自动提升为规则。映射项同样把说明／未知
放入其现有semantic_definition，不猜semantic_role。
不支持该注解的目标须由模型明确普通节点承载，不丢弃。

explicit_unknowns是候选级未决列表：保留在提交回执／缺口，若声明为本次必须可检索的
业务未知，则必须有被选ordinary entity及显式关系承载；程序只能检查明确引用，不推理
覆盖。没有这些绑定不得宣称未知已入库或候选已完整。阶段未选项及全局未知继续留既有
handoff／地图，不能以程序成功宣称全部业务完成；源事实是否齐全仍归独立语义验收。

引用只在声明的引用槽位解析；自然语言里出现IRI不等于引用。entity.properties的键
本身为属性引用时，使用既有单值属性表示的条目数组`[{property_ref, value}]`在转换边界
规整为真实property IRI键的object；不接受同属性重复值／冲突。该数组是中性引用到现有
properties字典的机械适配，平台payload仍只能object。字面量字符串保持字面量；对象关系
用relation项，不从字符串形状提升IRI。映射嵌套定义只转换010已声明IRI引用位置。

### 4.2 现有变更操作矩阵

fields只携带对应现有handler允许的业务修改字段，移除资源ID／IRI及ontology等技术字段，
由target_ref填回身份；所有unknown字段拒绝。缺省、null、空串、空数组严格沿每个compiler，
不能套通用patch语义。完整字段表引用`modeling_handlers.py::ALLOWED_FIELDS`及现有batch
reference；实现需同步遗漏的update／delete文档，不发明handler不支持的字段。

| resource_kind | action及映射 |
| --- | --- |
| entity／property／class／relation_type／operation | create／update／delete映射现有同名命令；统一图create仅前三节允许的entity／property，其余使用现有字段载体，不扩展统一图item_kinds |
| table_mapping／join_mapping／enum_meaning／metric_definition | create／update／delete映射现有同名命令；身份种类保持 |
| relation | create／delete映射create_relation／delete_relation；无update_relation。变更方向／端点显式delete+create，不自动拆成两批；三元组目标从获准读取的实际statement绑定 |
| fact | set_fact／delete_fact映射update_fact／delete_fact；target_ref指获准读取的实际事实条目，主体、predicate和旧object及IRI标记来自该条目。set_fact的fields为new_object_value与new_object_is_iri（IRI值须真实绑定），删除fields=null；不把update_fact变成无旧值upsert |
| mapping | 只保留现有普通Mapping可用字段；source_id／run_id导入变体现已被registry拒绝，仍返回unsupported_batch_variant，不绕过handler |

create额外语义载体只适用于现有Class／relation_type／Operation／普通Mapping能力，字段
沿现有compile_*；没有新的业务类型。技术ID由程序填；新资源不按label／item_id合并。
已有事实的覆盖／资源删除沿现有影响、保护与授权校验；没有关联项不会自动清理。若现有
删除handler需要impact_receipt，用已有获准读／影响检查程序取得，不让Agent拼回执；
不能据dry-run退役省掉真实删除范围／保护校验。

### 4.3 源字段对应、排序与引用

compiler生成§3.3的source_map并交给Executor；提交digest、原candidate item identity、
可选change_id、artifact及字段JSON Pointer贯穿编译、转发与反馈。一项多命令按批次
定位，反向映射保留所有来源；技术默认错误定位到change或request，不伪造源字段。

先对整提交做格式、意图、引用、字段／种类、已知授权scope、业务确认绑定闭合；可静态
确定的任何错误在首次apply前返回。编译不判断业务必要性或全面语义覆盖。确认过的字段
完整进入编译结果或报告未交付，不能静默跳过“不认识的”项。

依赖由显式引用／现有命令约束产生，稳定拓扑排序以原changes顺序、item顺序打破并列。
按已确认Ontology和部署modeling_batch_max_items分批，每批只针对一个Ontology。跨批binding归§3.3的Runner能力层，不归Executor。

- 同批outputs引用使用现有平台item-output reference合同；若特定命令不支持该槽位引用，
  改为先成功建立依赖再绑定，不发明平台$ref语法。depends_on只指同批client_item_id。
- 既有／跨批依赖来自实际获准回执输出；新create若必须提前绑定，Runner绑定层调用真实
  outputs_for配部署Settings和显式程序ID，保持future身份，不能称资源存在。实际输出
  与预期不一致时保留已写结果并停止依赖，原身份对账，不用猜测值继续。
- 引用环不一律拒绝run：先创建不带可后置字段的普通定义，再用已有update／关系操作
  完成显式引用；仅在原意允许该阶段状态且handler支持时如此分批。无法拆开的必填环
  返回`unresolvable_dependency`和原路径供作者修正，不编造Class／删掉条件。
- 显式delete+create替换若要求同批原子且不能同批编译，返回`atomic_dependency_conflict`，
  不自动分批造成旧关系先丢失；其他分阶段成功保留真实未完成项。

底层每批只发一次apply_atomic；服务内compile／校验是该次请求组成部分，不是第二次
平台执行。不得复用旧execute的dry-run／proof或翻译approval门，也不在纯编译阶段调用
模型写入。静态全提交检查不等于跨批事务，写入期间版本／权限变化仍可阻塞后批。

## 5. 持久身份、错误与执行结果

### 5.1 提交去重与可继续性

在现有run目录和intent／receipt中追加本次不可变提交及派生计划，不让Agent维护计划。
submit digest包含完整request、候选实际内容、已确认拓扑／业务决定绑定、选定目标内容，
不含lease／当前版本；同run相同提交找到同一记录。原始请求先落盘，再转发底层Batch；
快照／intent落盘失败则不转发。并发同提交复用既有Runner串行提交段及平台幂等约束。
Batch／幂等身份由Executor产生并先持久绑定，重启加载原值，不按重启时间生成。
client_item_id由compiler保留原candidate item identity（无candidate时为原change_id），
Executor不再生成或改写；仅向平台create payload填真实技术资源身份。

相同成功请求返回原资源／Attempt，不重放；查询当前索引可补新的观测时间，不改写原写入
revision。相同身份不同语义内容返回idempotency_conflict。已验证无写入的失败才可用新
Attempt；修正后的内容是新提交修订。若只调整技术lease／expected_revision，保持原语义
提交关联并保留失败Attempt，先获Modeling对版本漂移后的原意核对，再建技术Attempt。
平台失败Batch不可再次apply时新建技术Batch，不能卡死同一目标。

多批已成功部分以原change/item内容绑定复用；候选后续修订的显式update绑定原资源，
不是把之前create再执行一次。若原请求结果未知，冻结**受影响写入／依赖**的新尝试，
沿现有Batch／Attempt／资源／恢复记录对账，必要时调用原请求恢复；不扩大成整个run
不可恢复死亡。无需新恢复框架，保留第一阻塞层及原失败证据。

### 5.2 返回合同

程序返回封闭顶层`schema_version, submission_ref, submission_digest, status, batches,
errors, pending_changes`，版本`r4-3-025-model-change-result/v1`。
status为completed／not_written／partial／uncertain，仅描述执行，不描述语义通过。
completed表示所有选定change确认应用（或原成功复用），不表示所有候选／未知已建模。
not_written表示本次全部确定未写；partial为有成功且有明确未写／未执行；任一无法确定
批则uncertain，仍保留已成功和未执行明细。

每批包含`ontology_id, change_ids, batch_id, attempt_id, write_state, attempt_status,
resource_bindings, model_revision_before, model_revision_after, retrieval_indexes, receipt_ref`。
未创建Batch或未写时ID／after可null；write_state为not_written／applied／uncertain。
resource_bindings逐项含change_id、item_id（可null）、resource_kind和**实际**resource_id／
resource_iri或实际statement／fact定位；准备输出仅在原intent，不伪装成applied资源。
原始平台响应随既有receipt保留；不改写Attempt／recovery状态。

| 观察 | 写入判断／下一步 |
| --- | --- |
| 转换错、拒绝、validation_failed且无写／已确认完整补偿 | not_written；保留Finding和Attempt，修正后继续 |
| applied且有绑定终态 | applied；实际after来自该Attempt；信任回执，不要求逐条成功核验 |
| applying／recovering、超时、恢复证据不能确定完整补偿 | uncertain；按原身份对账，不能因failed字符串就声称全未写 |
| 写入已成功而索引failed／空 | applied；索引分别failed／unknown，不重复apply；查询是否降级由024与查询实际响应决定 |

当前上下文读回如果比写入after更新，只作为带来源／观测时间的补充，不能覆盖该Attempt
的before／after。retrieval_indexes保持平台实际结构，缺少状态为unknown，不把[]当ready；
不承诺向量立即就绪或自动等待／重建。后续025工程验收做真实受治理读取；正常Modeling
成功路径仍依015信任绑定回执，024自查不是逐条机械核验。

errors每项为`code, change_id, item_id, path, message, expected, actual, platform_ref,
retryable`；不适用值null。path定位冻结request／candidate的JSON Pointer，请求级错误
path为空字符串。平台Finding的client_item_ids／path经source map反向转换；group关联
多个项则逐项列出，原Finding不丢失。无源字段的capacity／权限／lease／版本错定位
change／提交，返回底层类型及可行下一步。受保护内容不在actual／建议里泄露。

错误归因继续按AGENTS四类；普通输入／平台合同错不是modeling-quality结论。程序输入
不完整只阻止受影响提交安全写入，角色／失败次数／消息顺序不加硬门。

## 6. 联动交付、验证与停止

后续开发授权下的最小实施序列：

1. 在当前统一图reference、012／010引用处补value／引用槽位和七类种类一致性、变更／
   结果合同；同步batch reference缺失的现有变更字段及索引／修订说明，历史文件不重写。
2. 实现纯compiler输出batches／source_map及稳定ID；DirectModelExecutor再接现有
   Session／lease、intent／receipt／apply Attempt proof和恢复调用；Runner能力层闭合真实binding／outputs。禁止调用旧格式validator强迫改写候选。
3. 024接真实Modeling能力、runtime目录及读代理，退役公开dry-run／proof／翻译审批／
   Protocol等待门。025程序核心自身不得依赖这些门；未联调前不宣称024完成。
4. API／MCP如受影响同步接口文档；不预设新增HTTP接口／UI／存储。仅实际必要代码改动
   才承担相应全量测试与服务重启。

权威A1—A10是验收主表。工程证据应至少包括：

- 七类统一图及既有变更的实际编译输出，原字段／注解／显式未知对照；不要只用schema
  PASS。设置同名不同item、未选择旧item、缺标签、relation字面量／对象混淆等反例。
- 当前registry真实outputs及实际配置；至少两个Ontology、生成身份、嵌套引用／容量分批；
  同批末项失败无部分写和后批失败保留成功前批，均核对底层真实调用及资源状态。
- 引用读权限、过期绑定、版本冲突、lease冲突、重复提交／并发／重启、未知结果原身份
  对账、索引失败；部分可用隔离故障注入，但原子apply／读回须有真实平台工程证据。
- 合法调用轨迹只有apply_atomic；无dry_run、翻译approval／Protocol中介调用。手写计划
  fixture可作底层回归，不算Modeling无需写计划的集成证据。

复用既有`test_translate_candidate_to_batches.py`、`test_r30009_unified_graph.py`、
`test_r3006_unified_binds.py`、plan-ref／staged forwarder及backend Batch系列测试；新测试
针对真实变化，不重建Harness。backend执行代码改动须`cd backend && uv run pytest`；
Team从backend运行`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests`。
后端／共享配置变更按AGENTS测试后重启并检查8001 health／5173；文档本轮不运行这些。

025工程通过、024真实工具采用／自查、独立最终源忠实／语义质量、同条件耗时收益分别
记账。A10真实任务需要另外授权；本设计不消耗或追加建模轮次。独立最终语义验收不
参与生产run的创建／继续／修复。设计通过且文档检查完成即停止，不进入实施。

## 7. 本轮设计验收状态

需求和设计已形成；原D1—D8独立设计验收Round 1 PASS保留。用户后续明确compiler／
DirectModelExecutor边界，新增D9，独立Round 2 PASS保留。后续进一步确认嵌套source_map、
侧车投影、跨批绑定归能力层及准确capability入口，已同步§3.1／3.3和相关要求；本次
独立设计**Round 3 PASS，0 Critical／High、无关键未决假设**，不以Round 2旧摘要
覆盖该修订。A1—A10均未执行。
见[独立验收记录](../records/2026-10-15-r4-3-025-design-review-record.md)。

本次只同步需求、设计、tracker和验收记录。未改活跃合同、Skill或产品代码，无需产品
测试／服务重启；文档及设计检查不证明执行工程、024实际采用或真实语义效果。

## 2026-10-20 增量：拒绝请求的显式小范围纠错

用户要求解决跨轮反复发参失败，新增request_ref上的可选request_edits输入。
静态compiler错误提供被拒正文的不可变correction引用、仅涉及控制键无损搬运的可选
suggested_edits和实际资源／操作字段合同。Agent显式提交add／replace／remove／move，
程序在副本上确定性应用；冲突值、业务内容和不支持字段由Agent处理，不静默修复。
派生完整请求仍经过原compiler／授权／application、成功去重和不确定写入对账；
既有request／request_ref兼容、请求版本及六字段不变。原设计审阅不扩成此增量独立验收。
实现和验证见[记录](../records/2026-10-20-modeling-input-correction-repair.md)。
