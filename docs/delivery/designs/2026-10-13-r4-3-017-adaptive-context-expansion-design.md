# R4.3-017 自适应相关子图扩展设计

日期：2026-10-13。权威范围：[R4.3-017](../../requirements/requirements-v4.3.md#r43-017-jev-参与分支选择的自适应相关子图扩展)。
代码基线：`61ccc5a`，定向阅读实际入口；本轮只改需求与设计文档。
状态：独立 Round 2 完整复审 PASS，0 Critical／0 High、无未决关键假设；原 Round 1
REVISE 保留，H1 在设计层面关闭。未实施，未进行工程或真实语义验收。
用户后续授权修改方案直至独立审阅通过；本轮不启动外部评分、建模、Consumer／Judge 或前端开发。
决策主记录为需求中的 D1—D8，本文件说明实施合同，不另建一份决策理由表。

## 1. 目标、最小方案与依赖

例如查询“关闭工单需要满足哪些条件”，主命中邻近的“调用绑定”可能只是导航入口，
“普通说明”可能没有进一步价值。第一跳均保留；Jev 选择调用绑定继续读取规则，再沿
有价值的规则分支取得例外或明确未知；普通说明可停止。节点和连边全部来自已有模型。

最小方案是在现有 Context Query 中加入 adaptive 分层选择，复用 RDF 读取、完整语义
hydration、授权、结构化映射引用、进程内快照与双分页。固定深度路径继续可显式选择。
采用两类评分解决当前真实歧义：不能直接回答的桥梁仍可能值得继续探索。

| 可行方案 | 行为与取舍 | 结论 |
| --- | --- | --- |
| 固定三跳再按相关度过滤 | 只改善返回体，已支付所有三跳读取成本，也不能证明逐分支停止 | 不满足本条探索要求 |
| 仅按回答分数推进 | 简单，但会剪掉低直接回答价值的必要入口 | 不采用 |
| 回答／探索分别评分，逐层选 frontier | 增加导航量表及选择状态；能够在读取下一层前停止分支并保护桥梁 | 本期方案 |

自然语言默认 adaptive、固定深度可显式选择、IRI 不涉及本条，沿 D1 用户决定。
前端先不改，沿 D8 用户决定。图展示需求保留到后续前端大改，API 的子图集合可作为
其输入；本期不增加图路由、图存储、业务关系白名单、Agent 编排或模型写入。

本条不依赖 R4.3-018 先实施。选择后的 related_context 仍用既有稳定顺序；018 后续
负责在其有界周边集合上按回答相关度排序。探索上下文中的分数不能直接冒充该全局排序分数。

## 2. 现有实现与增量位置

以下均为代码阅读事实，不是已运行验证。

| 入口 | 当前能力 | 本条最小增量 |
| --- | --- | --- |
| [SemanticContextQueryService.query_multi](../../../backend/app/services/semantic_context_query.py) | 多表达式、词面／向量召回、主命中 Jev 重排、根页恢复 | 解析默认策略／depth，维护请求预算，进入 adaptive 分支 |
| 同文件 `_expand_multi_primary`／`_related_for_root` | 每根独立固定遍历、合并周边与最短 root_paths | 多根分层 frontier，冻结选择；复用现有固定分支 |
| 同文件 `_neighborhood_chunks`／`_resource_item`／`_hydrate_candidates` | 请求内完整邻接和资源缓存、批量端点说明、完整值授权 | 同一节点读取复用，记录已读实际边和可复用的逐层候选 |
| 同文件 `_structured_reference_items` | 固定映射字段中的 source→target 引用、稳定派生身份、授权 | 在每个获准展开资源上提取既有字段，参与下一层；不添加反向全库 JSON 搜索 |
| 同文件 `_operation_target_context` | 已有基础上下文生产器 | 一跳结果保留；只有取得真实连接依据的端点进入自适应路径，不按返回来源猜造边 |
| [semantic_jev.py](../../../backend/app/services/semantic_jev.py) | 候选隔离、完整输入、30 KB 单问题／60 KB 分批、模型一致性及有界快照 | 具体分支评分方法与双量表；允许传入共享剩余时间，保存子图快照 |
| [semantic_context_cursor.py](../../../backend/app/services/semantic_context_cursor.py) | 当前 v3；签名、主体／查询绑定、根页恢复、ranking_snapshot_id | 策略与选择配置绑定、context_snapshot_id；保持稳定错误合同 |
| [semantic_access.py](../../../backend/app/services/semantic_access.py) 与 ranking_cache_key 调用点 | 每请求有效授权解析；当前排序 key 直接传入 asdict(access_view)，包含完整无权集合 | adaptive 保存服务端旧授权视图，控制变化时比较实际可见源内容；缓存定位不以完整无权集合哈希公开失效 |
| [REST schema](../../../backend/app/api/schemas.py)、[REST handler](../../../backend/app/api/semantic.py)、[MCP](../../../backend/app/mcp/tools/semantic.py) | 同一服务，REST full／MCP compact；depth 目前缺省 1 | 增加策略、缺省 depth 的解析；不改 IRI 路径的实际行为 |
| [能力发现](../../../backend/app/services/semantic_context_capabilities.py) | 深度／分页／5000 可见工作项预算与展开状态 | 公布策略、默认解析、选择版本／预算与完整性边界 |

已有身份去重、邻接复用和主命中缓存不计为本条新增收益。现有缓存不保存周边；
现有周边续页会再次 `_expand_multi_primary`，不能在其后直接加随机选择而不冻结子图。

## 3. 请求与默认解析

复用 `POST /api/semantic/context:query` 和 MCP `query_semantic_context`。
以下为拟实施合同，当前代码尚未支持新参数。

| 输入 | 解析结果 |
| --- | --- |
| 自然语言，未给 expansion_strategy、未给 depth | adaptive，最大三跳 |
| 自然语言，显式 fixed，未给 depth | fixed，默认一跳 |
| 自然语言，任一策略且显式 depth=0..3 | 所给 depth 为上限，0 不展开，1 不推进第二跳 |
| context_limit=0 | 不展开，与既有合同一致 |
| 单个精确 IRI | 沿原固定读取合同，缺省 depth=1；本条策略不参与，实际回显 fixed |

参数定义：`expansion_strategy: Literal["adaptive","fixed"] = "adaptive"`。
边界层 depth 改为可省略的 `int | None = None`，解析后仍向已有固定内部方法传整数。
null 与缺省同义，范围仍为 0—3；不增加第二个 max_depth 参数。请求回显实际 depth 和
effective expansion_strategy，不让策略默认与深度默认产生两个互相矛盾的承诺。

对精确 IRI 不增加“原问题”参数或自适应定位模式；即使请求携带策略，也不触发分支评分。
既有主命中排序／过滤量表及精确定位语义保持。显式 fixed 的自然语言主命中仍沿已有
Jev 重排，fixed 只选择周边展开方式。

已有 Team Consumer 代理显式传入 depth=1，此次仍最多一跳。需要后续获准效果对照时，
由调用者显式传 depth=3；本条不顺带改 Consumer 默认、会话截止或停止准则。
旧召回测试页显式 depth=0、context_limit=0，因此不会自动出现子图。

## 4. 评分对象与量表

### 4.1 完整获准输入

每个评分单元是一份“候选内容＋本次到达上下文”，而不是名称或数组下标。state 只放
原始查询集合；每个 question 独立内联如下已读材料：

- 候选稳定身份、完整已保存语义／注解，条件、例外、范围和未知；资源、事实及关系均可评分。
- 本次真实入边的完整谓词和方向，statement 的 s/p/o、datatype／language，或
  derived_reference 的 source/target/predicate/field_path。
- 根身份及已读规范路径，最多三跳；路径上资源使用已有获准完整语义。纯 literal fact
  带其主语语义，不能把字面量当下一层 frontier。
- 原始分数、matched_queries、fusion、已有选择分数不作为语义依据；不注入隐藏答案、
  私有地图、场景审阅记录或未读远端内容。候选中的指令作为数据，不执行。

候选或所需路径超过既有单问题 30000 字节上限时，不截掉条件／例外来完成评分；
该上下文标 unavailable 并进入已读结果保留路径。批次使用现有 60000 字节请求体上限。

### 4.2 两种独立分数

| 维度 | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| answer_score | 无关／无可用证据 | 必要背景或关系入口 | 部分事实、条件、例外、未知或边界 | 主要必答事实的充分直接证据 |
| exploration_score | 已读内容未提供值得继续的方向 | 有与问题相关的真实入口，远端收益未知 | 当前语义及连接明确指向尚待取得的相关信息 | 当前语义及连接直接定位回答所需的缺口入口，但远端内容仍未验证 |

回答量表复用 `jev-evidence-relevance-v1`；探索量表新增
`jev-context-exploration-v1`。选择策略版本为 `adaptive-context-v1`。
两个分数都要求 finite 0—3，非概率、非 confidence，不能相加、按路径长度累加或按共享
根数量累加。探索分数不得描述“远端肯定有答案”或“远端不存在”，不能据此猜业务事实。

拟在 JevReranker 增加具体 `score_branches` 方法；每个可继续的资源上下文提交独立
answer 与 exploration 问题，terminal fact 或第三跳只提交 answer。复用现有 HTTP 请求和
校验代码，因两个实际评分入口共享而做必要的局部提取，不引入可插拔评分器框架。
现有主命中 score 方法和量表保持，新增实际方法名在实施时以最小实现机械对齐。

一次评分阶段所有批次必须使用一致的实际 upstream model；本请求主命中成功评分与
分支评分也不得混用不同实际模型。首个成功评分绑定模型，后续不同模型的批次丢弃并降级。
原始 HTTP 错误正文、凭据和受限内容不进入响应或诊断提示。

## 5. 分层选择与连接保留

```mermaid
flowchart LR
    A[既有主命中召回及排序] --> B[获准第一跳基础上下文]
    B --> C[Jev 选择第二跳入口]
    C --> D[读取选中入口的第二跳候选]
    D --> E[回答保留与第三跳探索分别判断]
    E --> F[读取选中入口的第三跳候选]
    F --> G[回答保留与必要连接闭合]
    G --> H[冻结子图与选择状态]
    H --> I[既有顺序和双分页]
```

1. 复用主命中结果，所有当前根均参与第一跳。第一跳由现有获准 RDF／引用／Operation
   上下文组成，在工作预算内无新增相关度淘汰。保留它的完整内部资源和已读边，页大小
   只用于最终投影。depth=1 时完成于此，不进行无用途的自适应评分。
2. depth≥2 时，对第一跳可继续的资源及其真实到达上下文做双评分，选择有探索价值的
   入口。只对选中入口读取邻接和既有结构化引用；未被选择的分支不读第二跳。
3. 对已读第二跳的资源、事实和关系判断回答价值；对可继续资源同时判断探索价值。
   回答合格的候选入选；有探索价值的资源按宽度规则继续第三跳。新真实入边可形成新的
   有效评分上下文，不能仅因节点已见而跳过。depth=2 时不算无用途的第三跳探索分数。
4. 第三跳只判回答价值，不再推进。保留入选证据的规范路径上节点和边，不因中间节点
   answer_score 低而断开。没有取得下游证据的低回答桥梁，不因曾被探索就自动视为答案。
5. 将第一跳、入选证据、必要路径、评分失败时已取得的合法内容合并；加入已经读取且
   两端均保留的真实连边，不再专门扫描整个选中节点集合之间所有未读边。
6. 先内部连接闭合，再遵守调用方 resource_types 输出筛选。内部遍历可穿过不输出的
   资源类型，assertion_types／授权继续约束读取。只请求 fact 不强制带回 relation 或
   instance；标记路径投影受筛选限制，不声称输出可还原完整图。
7. 继续用 `_context_sort_key`，最后冻结并截页。answer_score 不在本条改成周边排序键。

literal 是 terminal，谓词的 IRI 不是由该边隐式到达的节点。statement 主命中以实际
subject／URI object 作为展开端点，沿当前合同处理。结构化引用为真实 source→target
导航，进入深层节点时也可提取；不从任意 JSON 或只见 target 推导未取得的反向引用。
跨 Ontology 仅在当前获准 scope 内解析端点；同 IRI 多份定义分别授权、保存和评分。

### 5.1 环、共享和规范路径

使用下列有限请求状态，不把它们全部塞进一个 visited：

| 状态 | 键与用途 |
| --- | --- |
| visible_items／read_edges | 现有 `(ontology_id,kind,id)`；节点与边分别保存，保留真实自环／回边／交叉边 |
| adjacency_cache | 已完整读取的端点及 scope；跨根复用；半页不记为完整 |
| best_paths | 每根稳定身份＋候选身份的最短选中真实路径；同距离按实际边身份稳定裁决 |
| scored_contexts | 查询／候选完整值、根与规范路径／入边、量表及实际模型的摘要；相同有效上下文只评分一次 |
| expansion_state | 节点可见身份及已处理的剩余跳数；已见、待评分、策略停止、已展开、预算中止分别表达 |

不枚举全部简单路径或循环路径。新入边的评分上下文只按有限已读边及当前规范前缀生成；
回到已在该路径中的节点不形成一次新绕环任务。跨根输入确实不同可分别评分，完全相同
输入复用；合并结果不按通过了多少根评分增加相关度。

同一节点的新入口可以改变是否探索，但已读邻接继续复用。较短新路径增加剩余深度时，
在缓存上处理此前未覆盖层级；若规范输入改变，重新评分计入累计上限。对已取得候选，
允许其不同真实上下文独立入选，不取分数和，不把某一个上下文的拒绝写成节点永久拒绝。
root_paths 距离来自最终选中真实路径；被删除路径不能继续成为来源／距离依据。

完整内部 root_paths 始终保留 root_ontology_id、root_match_id 和 graph_distance，
避免跨 Ontology 同 IRI 根混淆。preview 按已有 root_index 投影到当前根页；页内下标
不作为跨页身份。内部路径表保留逐边引用用于连接闭合，公开 root_paths 不变成全路径枚举。

## 6. 初始选择配置、累计预算与结束状态

下表给出可直接实施的工程初值。它们不是已校准质量阈值；后续公开中文样本可在相同
量表和授权内调整，记录配置版本与对照结果，不重新打开 D1、D8 的用户决策。
首版放入一个具体选择配置，不增加面向用户的高级参数表或通用预算框架。
一个请求内所有根、批次及重访共用预算；context 续页仅返回冻结结果并保留原探索用量，
不追加探索。match 续页是新请求，可为新的根页使用一次相同限额。

| 项目 | 初值及语义 |
| --- | --- |
| 深层回答保留 | answer_score≥1，第二／三跳一致；必要路径与基础一跳免此删除 |
| 探索资格 | exploration_score≥1；低回答价值不等于无探索资格 |
| 向第二／第三跳推进宽度 | 当前根页全局最多 32／16 个去重端点；包含桥梁名额，不按根重置 |
| 桥梁预留 | 分别在上述宽度内预留最多 8／4 个 answer_score<1 且 exploration_score≥1 的端点；不足时剩余名额可用于其他合格端点 |
| 工作项 | 复用请求累计 5000 个授权可见去重资源／边／事实上限；不计隐藏项 |
| 评分上下文 | 请求累计最多 512 个分支上下文；每个最多两个标量问题，第三跳／terminal 可只问一个 |
| Jev 时间 | 主命中及分支评分共享现有 semantic_jev_timeout_seconds，默认累计 15 秒，不按批次／层重置 |
| 自适应工作截止 | query_multi 入口起的 30 秒软截止；检查和下一次调用使用剩余时间，截止后停止新增自适应工作并返回已有合法结果 |
| 快照 | 复用进程内总共最多 64 项、TTL 沿 cursor 默认 600 秒；根排序和子图都占该上限 |

资格端点以 exploration_score 降序、answer_score 降序、稳定身份／到达上下文顺序
选取；一个端点多个合格入口只占一个推进名额，不增加共享次数权重。先满足有候选的
桥梁预留，再用同一顺序填满其他名额；不因根排名额外赋予业务权重。

桥梁仅按已有语义的两种分数区分，不引入平台业务角色或谓词分类。探索宽度主动选择
属于策略边界，记录 `branch_width_limit` 及获准未推进入口，可供后续定向读取；它不是
“固定深度全邻域已取完”。评分／工作项／时间耗尽属于 partial，不能记为策略正常完成。

30 秒为新增探索的软截止，不承诺整个查询严格在 30 秒内结束：现有主命中召回仍有其
嵌入／SQL／RDF 超时合同。进入扩展时扣除已耗时间，超期不再开始自适应评分或深层读取。
新增 RDF 读取采用 `min(现有10秒, 剩余时间)`，Jev 采用共享剩余评分时间与软截止中的
较小值；不在本条改写所有检索客户端。完成必要的第一跳和响应前版本核验仍遵守既有
单调用超时，报告实际耗时；未能完成第一跳也按 partial 表达，不能保证无预算的一跳全量。

避免时间耗尽抹掉第一跳：主命中评分耗尽 Jev 时间时，基础一跳仍可按已有读取预算取得，
自适应深层标 degraded／partial；不得为了“必须 adaptive”而让整个正常读取失败。
认证／授权失败、源修订冲突继续沿原错误；自适应可用性失败不绕过这些硬边界。

## 7. 子图快照与续页

### 7.1 保存内容与绑定

复用 semantic_jev 的 OrderedDict、锁、TTL 和副本语义，分别保存两类具体记录：已有
primary ranking，以及当前根页的 context selection。两类共用 64 项总上限，子图按
独立记录逐页存，不在一个主命中快照中无限累积所有根页的 5000 项邻域。

子图 key 包括根排序快照身份（若存在）、原根页起点／root digest，以及原 binding、
scope／workspace／source 签名、主体／有效 Grant 绑定和选择配置；授权控制数据的有效性
在取用缓存前另行核验，不以“可见保护成员集合”作为覆盖所有可见性变化的签名。
固定 root_paths／实际关系／完整候选值摘要用于完整性核对，不使用隐藏集合的变化作
独立失效信号。结构化完整值、scope 与保护成员校验复用现有逻辑。

adaptive 不直接复制 ranking_cache_key 的完整 asdict(access_view) 输入，也不能只
用可见保护成员签名判断有效性。现有 remove_members 删除成员但不推进模型修订；
X、Y 都无权时，将 X 移出最后保护集会使 X 公开，但有效 Grant、可见保护成员及旧缓存
项的合法性都可不变。上一轮 H1 即此反例，不能用重查“已有缓存项仍合法”关闭。

采用下列局部核验，不新增授权表、控制数据修订机制、通用缓存或决策缓存：

1. 首次保存主命中／子图快照时，在服务端私有 payload 保存当次有效 SemanticAccessView，
   以及 scope／源修订签名。无权 IRI、控制差异及其摘要都不放入 cursor、响应、warnings、
   用量或外部评分输入；snapshot_id 仍是随机 opaque 身份。
2. 续页及重复首查先按现有 resolver 取得当前有效视图。主体／Grant 与请求、修订、索引和
   配置按既有绑定检查；在这些输入未变时，对比旧／新最终无权 IRI 集合，不以成员记录
   行、集合名称、updated_at 或 requires_filtering 单独判定语义变化。Admin 的 all_visible
   按空无权集处理；OR 覆盖沿 resolver 决定，不自行改写授权逻辑。
3. 有效无权集相同，沿原完整缓存值授权核验后复用，不重读邻域、不评分。无权集不同，
   在同一个已确认未变的源修订上，对旧／新视图做一次确定性实际源可见性对照。复用
   scope 所选图的稳定 RDF 分块读取，以 is_statement_visible 对同一完整四元组两次
   判断；嵌入 JSON 字面量沿现有完整字符串叶解析，含 Unicode 转义，不能只查 s/p/o
   IRI 或 member.ontology_id。既有非 RDF 上下文生产器的完整原值也按 filter_candidate
   对照，覆盖从该生产器读取的资源引用；不把不同源版本拼成授权反例。
4. 只要某条实际 scope 内源内容的可见性不同，说明受治理可见范围改变：旧 match／context
   cursor 返回 context_snapshot_changed；无 cursor 首查丢弃该绑定下旧主命中／子图快照，
   按当前有效授权重新召回和选择。源范围比本页已选结果宽，X 不必已在旧缓存中，移出
   最后保护集、删除保护集及 OR 覆盖变化均可被检出。被其他无权引用继续遮蔽的完整源
   内容两次均不可见时，不把该条当可见性变化。
5. 只有对照完整且实际可见源集合相同，才复用原冻结选择／分数／路径；可更新私有的
   最近已核验授权视图，不能重评分或修改冻结语义集合。仅无权成员在无覆盖集合间移动、
   受限 IRI 不在当前源内出现或相关原值在两视图下均不可见时，不单独发失效或泄露提示。
6. 对照使用已有 RDF／生产器超时和稳定补读，原始隐藏行不计可见候选预算，不能先截取
   一个原始窗口就宣布两视图相同；该核验不运行 Jev、不推进 frontier，也不额外枚举三跳。
   无法完整核验时沿 SemanticAccessDependencyError 的 dependency_error 返回可重试
   503，不输出未经核验的旧缓存或以降级绕过授权；不将核验失败误记为语义评分失败。
   复用前后仍检查当前控制视图与源签名未变，发生变化时不输出两时点混合内容。

这是“有效授权确有变化”时的必要源读取例外，正常续页仍只取冻结集合。对照可发现
任何实际可见源内容变化，不承诺只在当前问题一定命中 X 时才失效；未因纯隐藏变化
产生不同的源可见集合时不失效。它不把控制数据变更提升为模型修订，也不修改保护集
写接口、授权规则或运行额度。A5／A7 分别验证该例外与隐藏无痕；不得仅看 Grant 字符串。

保存当前完整根页及其后继 match cursor 所需元数据、检索索引签名、完整内部选中集合、
实际关系、规范路径、分数／实际模型／版本、最终既有顺序、部分／降级原因、已读未评分
结果和续读提示。主命中不重复进入周边，但仍参与实际边端点与路径连接。最终截页、compact
或 preview 不写回缓存副本，外部修改响应不会污染下一页。

新增 `context_snapshot_id` 到 context cursor 的签名 payload；自然语言 adaptive
绑定扩展策略、解析后的 depth、context_detail 与完整选择配置摘要。扩展和评分模型、
凭据身份、检索版本及预算变更不复用旧选择。相同绑定的首查可复用未过期子图，降级
快照同样复用，服务恢复不能让旧页突然换集合。

按当前 codec 的实际基线升级 cursor 为 v4，保留原错误代码；v3 旧临时 cursor 可按
既有 invalid_contract 要求重新查询，不增加跨版本恢复层。升级需在 API/MCP 文档中
明确，不能继续沿早期文档的 v2 描述；受影响的 fixed 续页也需重新首查。

### 7.2 续页步骤

1. 校验主体、scope、请求绑定、当前有效权限、源／模型修订及检索索引；按 §7.1 对照
   已保存的私有授权视图，实际可见源内容变化时要求重查，核验不完整按 dependency_error
   返回。重复无 cursor 首查也先做同样核验，不能复用新增可见内容之前的旧排序或子图。
2. context cursor 从子图快照恢复原主命中页与 context_snapshot_id；即使主命中 Jev
   没有产生 ranking 快照，也不为恢复根页重复召回／评分。获取该子图，重新对缓存的
   完整值作可见性核验并复核当前 scope。快照失效返回 409 context_snapshot_changed，
   不重评分来“凑出”原 cursor；源可见性对照也不改变原探索选择或追加探索预算。
3. 在冻结顺序中找到既有稳定 resume_key，再投影下一页。返回原根页之后的 match
   cursor；翻到下一根页时才首次执行该页探索。两种 cursor 仍不可同时传。
4. 固定深度仍走原确定性路径。自适应选择快照的存在不以主命中 Jev 成功为前提：即使
   Jev 关闭或主命中评分失败，也保存一跳／已读结果的降级子图，确保 context 页不漂移；
   Jev 配置／开关仍进入绑定。子图若引用 ranking_snapshot_id，续页也校验其未失效。

跨主命中页共享节点可重复返回，用于保留该页来源；API 不隐藏后页共有资源。
未来页面跨页累计按稳定资源／边身份合并，并累计根来源，不混合不同修订和选择配置。

## 8. 响应增量与失败反馈

维持 primary_matches／related_context 和双页结构，不新增顶层 nodes／edges 的第二套
语义数组。图可由实际 resource、statement、derived_reference 重建，literal 保持事实。

以下 JSON 为局部合同示意，非当前响应、非效果证据；数值仅展示字段含义。

```json
{
  "query": {
    "queries": ["关闭工单需要满足哪些条件"],
    "expansion_strategy": "adaptive",
    "depth": 3
  },
  "context_page": {
    "truncated": true,
    "next_context_cursor": "opaque-token",
    "expansion": {
      "status": "complete",
      "strategy": "adaptive",
      "version": "adaptive-context-v1",
      "completeness_scope": "selected_subgraph",
      "selection_status": "applied",
      "stop_reasons": ["depth_limit"],
      "path_projection": "paged",
      "scoring": {
        "model": "actual-upstream-model",
        "answer_version": "jev-evidence-relevance-v1",
        "exploration_version": "jev-context-exploration-v1"
      }
    }
  }
}
```

| 字段 | 拟实施含义 |
| --- | --- |
| expansion.status | 沿用 complete／partial／not_requested；complete 仅指当前选中策略完成，depth=0 或 context_limit=0 为 not_requested |
| completeness_scope | adaptive 为 selected_subgraph，fixed 为 requested_depth；两者都只在当前可见 scope／根页内，不证明业务完整 |
| selection_status | applied／degraded／not_requested；第一跳无需深层选择时 not_requested，不能误称 Jev 已决策 |
| stop_reasons | 保留已发生原因：policy_complete、depth_limit、branch_width_limit、expansion_budget_reached、scoring_budget_reached、time_budget_reached、scoring_unavailable；不覆盖首阻塞层 |
| path_projection | complete／paged／filtered／partial；预算未读完整优先 partial，类型过滤其次 filtered，冻结集合尚未全部返回为 paged；完整仅指实际保留路径，不保证图闭包 |
| budgets／usage | 回显版本化限额和本次实际可见累计用量，包括评分上下文、展开项、推进宽度和耗时；不返回隐藏数量 |
| resume_hints | 最多 16 个已知、获准的未推进入口 IRI／Ontology 和 stopped_at_depth／原因，按稳定身份排序；更多时标 hints_truncated，不提供未知远端 ID |

`resume_hints` 用于重新发起较窄自然语言查询、fixed 查询或原 IRI 读取；它不是可无限
延续探索预算的第三种 cursor。context cursor 只翻冻结结果页；末页无 cursor 仍可能 partial。
读回资源确实没有可定位 IRI 时不伪造 detail_query，由已存在 statement 主语详情入口处理。

related_context 行增量使用独立 `expansion` 元数据：retained_as 为
base_context／answer_evidence／path_bridge／connection／unscored 的非空列表；
score_contexts 保存有实际评分的有限上下文，含稳定 root 身份、真实 via_edge 身份、
path_digest、answer_score／exploration_score、scale、量表版本、实际模型和 status。
无评分为 null／unavailable 或 not_requested，不写为 0。只有路径保留而未独立评分的边
标记相应保留用途，不能复制端点分数冒充该关系评分。多个上下文不压成虚假的累加分。

root_paths 是来源距离，score_contexts 解释选择来源；实际关系项负责连接，二者均不
造直接边。元数据穿过 `_public_item`、compact、preview；preview 仍省略完整定义、
脚本和原始 JSON literal，不让选择依据把全文绕行带回。不得把这些分数放进主命中
match.relevance_score 或改变既有 confidence／score 含义。

### 8.1 可恢复降级

- Jev 配置不可用、key 缺失、HTTP／超时／无效分数／单候选过大：保留已有合法结果，
  对受影响上下文标 scoring_unavailable，停止其深层推进。上游不可用时停止本次新的
  评分；单候选过大不让其他已成功上下文失效。不自动增加重试或额外预算。
- 批次中某些答案缺失或无效：该批不得用于选择；之前已校验的批次及路径保留，未评分
  已读候选作为 unscored 合法内容保留。实际模型漂移的批次同样不得混入选择。
- 预算中止／新增 RDF 读取失败：不将半邻接缓存为完整，保留已读合法内容及 partial
  状态；已知获准入口进入提示。版本核验失败或授权错误继续返回原错误，不能借降级
  输出失去资格的缓存值。
- 降级有已有可分页结果时仍提供正常 context cursor；没有页剩余时不造 cursor，保留
  partial／degraded 及已有入口。无根匹配沿原召回状态返回，不以扩展评分证明知识不存在。

## 9. 实施交接与验证意图

最小改动归属为后端 Context 服务、Jev client、cursor、REST/MCP schema／handler、
能力发现与对应 API/MCP 文档。配置初值在后端具体选择配置中维护，修改时改变绑定版本；
不修改前端、数据库迁移、业务模型、既有 Team 运行授权或相邻 018 实现。
文档设计不执行 GitNexus 代码影响分析；开发修改公共合同前按 AGENTS.md 做影响分析，
可用时用精确文件／符号定位，若返回 HIGH／CRITICAL 先报告，不能把设计自查当代码覆盖。

实施顺序与验收对应：

1. 默认解析与固定／IRI 分支，REST、MCP、能力发现合同及回归（A1、A9）。
2. 双量表、完整候选与共享时间，批次错误及模型版本校验（A3、A8）。
3. 分层 frontier、结构化引用、共享邻接、环与必要路径闭合（A2—A5）。
4. 有界子图快照、v4 cursor、续页和授权／修订失效（A6—A9）。
5. 更新当前 API/MCP 使用说明，执行要求的后端全量 pytest、重启及受影响端点验证。
   这一步是后续开发交付门，本轮未执行，文档变化不需要重启。

复用 `test_r4008_context_query.py` 的真实 SPARQL DatasetStore、
`test_semantic_jev.py` 的 HTTP stub 和 `test_semantic_context_query_api.py`／
`test_semantic_context_query_mcp.py`／`test_semantic_context_cursor.py`；按行为增补用例。
工程测试用确定性两种分数验证选择与预算，记录邻接调用以证明未读被剪枝的层；
不能仅断言结果变少或候选排序正确。

真实效果 A10 由后续授权运行独立判断：固定相同主命中候选、scope、修订、公开中文多跳
问题和预算，对照 fixed depth=1、fixed depth=3、adaptive depth=3；再检查实际 Consumer
端到端表现。主命中候选相同的对照隔离扩展收益，端到端对照披露召回本身的变化。
记录必要事实及路径、桥梁／条件／例外／未知的保留和具体漏项、实际补读次数、输入输出
token、HTTP／邻接／评分／总耗时以及降级比例。先记录对照结果再给效果结论，评分器
或作者自评不代替独立业务标准；不使用隐藏题做阈值调优，不因子图小宣布质量提升。

没有具体性能提升幅度已获确认，本期不虚构百分比门槛；工程正确和默认采用可以先形成，
效果仍须如实保留待证。若出现必要条件／未知或路径退步，保留具体反例与版本，不从
默认使用决定推出质量 PASS。校准值、响应字段实现名可在上述冻结含义内机械对齐，
用户已确认的默认模式和前端边界不重新打开。

## 10. 检查、独立审阅记录与完成边界

本轮需求／D1—D8／本设计／A1—A10 已作一致性自查；新增本地链接、Markdown 围栏、
局部 JSON 示例及 diff 已检查。未运行产品测试、外部 Jev 或服务重启。
检查只证明文档与拟实施合同一致，不证明检索选择正确、性能改善或真实业务语义 PASS。
后续前端展示仍待其改版授权，R4.3-018 仍保留登记状态。

| 轮次 | 范围与结论 | 问题及修订 |
| --- | --- | --- |
| Round 1（2026-10-13） | 独立 plan_reviewer；提交 5106ea0；REVISE，0 Critical／1 High，无待用户决定的关键假设；只读，无测试或运行调用 | H1：§7.1 的“可见保护成员＋有效 Grant”签名不能发现解除最后保护后的新增可见内容；remove_members 不更新模型修订，缓存完整值复核只覆盖旧项 |
| Round 2（2026-10-13） | 同一独立 plan_reviewer 完整复审；5106ea0 基线上的本轮 H1 修订稿；PASS，0 Critical／0 High，无未决关键假设；只读，无测试或运行调用 | H1 在设计层面关闭：服务端旧授权视图与同修订实际源可见性对照检出解除最后保护；纯隐藏变化保持冻结选择，授权核验失败可重试；A5—A7 已覆盖反例、故障与必要源读取例外 |

Round 2 送审时需求文件 SHA-256 为
`f4b3c7be39cb0765543173bfa4d084849a9ee0a331a2895281d394f076dde1ea`，设计文件为
`ce3e35e2a226bfc3e1659a1f57d90408f7e3af3d69bda59f6d61c16112e11619`。
复审结束前两文件未变化；PASS 后仅更新状态及本审阅记录，需求的目标／F1—F7／D1—D8／
A1—A10 与设计 §1—§9 未改动。独立覆盖原登记及依赖、评分时序、桥梁／必要路径、环／共享根、
累计预算、授权、双分页、降级与 REST/MCP；本结论仅为设计 PASS，工程和真实效果仍待验证。
