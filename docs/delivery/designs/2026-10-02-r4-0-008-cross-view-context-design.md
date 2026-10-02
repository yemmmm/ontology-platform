# R4.0-008 跨视角语义检索与上下文组织设计

## 1. 状态、依据与目标

- 权威范围：[R4.0-008](../../requirements/requirements-v4.0.md#r40-008-跨视角语义检索与上下文组织)。
  同文档的 002—007、010—012 是表达、授权、协同及追溯停用边界；
  [R3.0-004](../../requirements/requirements-v3.0.md#r30-004-主体绑定的语义知识访问控制)
  规定无权与不存在不可区分。
- 代码核对基线：`11b4e32`，2026-10-02；开始时工作区干净。本轮只完成需求细化与设计，
  未实施、未启动服务／建模、未执行功能或真实语义验收，也未开展独立方案审阅。
- D1—D8 的完整决策与来源保存在权威需求中；本设计不另建一份决策表。

例子：一个流程两次调用同一个“关闭工单”Action，分别处理原工单和返修工单。Consumer
应能沿流程、调用、参数绑定、值引用取得各自的对象来源，继续读取规则、职责和已有关联映射。
共享 Action 只需一份定义，但两个调用点与绑定必须保持独立身份。平台提供可验证的关系和
说明，Consumer 解释业务含义；没有返回关闭规则不能推出“可无条件关闭”。

最小方案是在已有 Context Query 中补齐角色筛选、注解投影、受治理邻域和分页完整性。
不新增存储表、资源类型、专用查询路由、流程返回树、业务关系白名单或执行引擎。

## 2. 现有能力与具体缺口

以下为定向代码阅读结果，尚不是运行复现或测试结论。

| 入口／符号 | 当前基础 | 本条需要补齐 |
| --- | --- | --- |
| [`SemanticContextQueryService.query_multi`、`_query_anchor`](../../../backend/app/services/semantic_context_query.py) | 多表达式融合、单 IRI 锚点、主命中与上下文双分页 | 语义角色筛选、主命中和关联资源统一注解投影 |
| 同文件 `_related_for_root`、`_expand_neighborhood` | 双向邻接、Shape／Operation 相关生产器 | 当前每个生产器先按 `context_limit` 截取，外层游标不能恢复未枚举项；需与页预算解耦 |
| 同文件 `_expand_neighborhood`、`_expand_multi_primary` | 先展开、后用 `filter_candidate` 过滤结果 | 隐藏中间节点不得进入 frontier；输出类型过滤不得提前阻断合法关系遍历 |
| 同文件 `_public_item`、`_compact_related_row` | full／compact 及 root_paths | `_public_item` 不透传顶层 description；compact 仅留部分 statement 字段，缺 subject IRI、Ontology、datatype／language 等；必须补齐身份与含义 |
| [`semantic_sparql_templates`](../../../backend/app/services/semantic_sparql_templates.py)、[`SemanticReadModelService._detail_fields`](../../../backend/app/services/semantic_read_model.py) | entity 等读模型已投影／解析语义与 Action、参数、规则 JSON 注解 | Context Query 不能只依赖邻域中的原始 JSON literal，应复用同一字段含义 |
| [`SemanticAccessView`](../../../backend/app/services/semantic_access.py) | 对资源、statement 与嵌套 JSON 中的明确 IRI 进行过滤 | 补投影后仍先检查完整值，之后才 compact；路径与描述不能成为旁路 |
| [`semantic_context_cursor`](../../../backend/app/services/semantic_context_cursor.py) | 主体、Grant、scope、查询、过滤、预算、版本绑定及错误合同 | 绑定新增角色筛选；保护成员变化须校验当前可见集合，不能只看 Grant 字符串 |
| [`semantic_context_capabilities`](../../../backend/app/services/semantic_context_capabilities.py) | 已有参数上限和游标能力发现 | 声明新增筛选、投影与展开预算语义 |
| [`semantic.py` REST](../../../backend/app/api/semantic.py)、[`semantic.py` MCP](../../../backend/app/mcp/tools/semantic.py) | 共用查询服务；REST 默认 full，MCP 默认 compact | 同步新增参数与投影行为，保留既有默认差异 |

业务规则由 005 写为普通实体的 `rule_definition` 注解；Context Query 的 `kind=rule`
还承担既有平台 Rule。不能为了召回业务规则把普通实体改造成可执行平台 Rule。
004 的调用／绑定／值引用使用普通节点与谓词，008 必须读其实际结构，不能另建流程解析器。

## 3. 请求合同与结果组织

### 3.1 请求

沿用 `POST /api/semantic/context:query` 与 MCP `query_semantic_context`，保留所有既有参数。
新增一个可选参数：

| 参数 | 合同 |
| --- | --- |
| `semantic_roles` | 缺省／null 不筛选；非空字符串列表，trim、去重，按明确 `semantic_definition.semantic_role` 匹配，区分大小写，多值 OR。不注册平台角色枚举。空列表／空字符串按既有参数错误处理 |

角色筛选与已有 `resource_types`、`assertion_types` 在主命中上取 AND。只保留具有实际
角色声明的资源，不把 statement 的主语角色当作该 statement 自身角色，不从名称、Class、
调用关系推断角色。角色声明批量读取并授权后，在融合排序、匹配预算及匹配游标之前筛选；
hybrid／lexical／精确标签提升／IRI 锚点均采用相同规则。未知角色合法，返回正常空匹配。

`semantic_roles` 只筛主命中；关联上下文不继承此筛选，否则搜索 Action 会丢失参数和规则。
`resource_types` 与 `assertion_types` 继续限制最终输出；遍历获准关系可跨过不输出的类型，
但不能跨过被 assertion 选择排除的图，也不能跨授权边界。只请求 fact 会主动放弃关系输出，
因此不能据此声称已获得可还原路径的完整图；它仍可到达关系另一端的事实。

`depth` 仍为 0—3、默认 1；`limit` 默认 20／最大 100；`context_limit` 默认 100／最大
1000，允许 0。不提高默认展开深度或增加自动全流程模式。能力目录同步明确这些边界。

### 3.2 资源与 statement

沿用 `primary_matches`、`related_context`、`root_paths`，不另加七个视角数组。
资源身份使用现有 IRI／Ontology，statement 使用现有 quad 身份；去重至少保留
`(ontology_id, kind, id)`，不能按 label、角色或 Action IRI 合并不同调用节点。

资源的 `data` 增量复用以下已有字段：

| 字段 | 来源与行为 |
| --- | --- |
| `semantic_definition` | 既有 `semanticDefinition` JSON：role、business_meaning、applicability、unknowns、not_applicable、conflicting_meanings；原样保持含义 |
| `action_definition` | 003 已保存的 Action 注解；对象、参数及外部能力仍以明确关系引用 |
| `parameter_definition` | 003／004／005 已保存的参数方向、基数、必填及值约定；不替代参数身份 |
| `rule_definition` | 005 已保存的规则分类、脚本及执行约定；供读取，不触发运行 |

同时保留已有 description。资源 hydration 只读取已有语义注解及说明，不导入场景地图、
owner、review、Grant 或角色目录。未存字段保持缺失，显式 `unknowns`／`not_applicable`
保持其原值；不自动填充空数组并解释为“已确认没有未知”。

statement 的 s／p／o、object_type、object_datatype、object_language 和图／Ontology
定位保留，不能用标签替代身份。资源输出保留 `target_kind=resource`，事实／关系断言
保留 `target_kind=statement`；`kind=relation` 本身不足以区分关系定义与关系断言。
`root_paths` 只给根命中与距离，不能称为完整逐边路径；Consumer 使用返回的 statement
连接业务引用。关联资源可聚合多个获准根路径，同一根的重复路径按最短距离去重。

### 3.3 full／compact

两种投影不改变命中、排序、页集合、身份或授权。`context_detail` 对现有主命中继续使用
full 返回；对 `related_context` 选择 full／compact，避免悄悄改变旧主命中的投影语义。
因此 MCP 默认 compact 也可能在主命中为规则资源时返回脚本；需要正文最小化的调用者
应理解该边界，本期不新增全响应脚本屏蔽开关。

| 项目 | full | compact 关联行 |
| --- | --- | --- |
| 资源／statement 身份、Ontology、断言类型、方向及 literal 类型 | 保留 | 保留；补齐旧 compact 缺失的 subject 等字段 |
| 业务说明、角色、范围、未知／冲突、参数约定 | 保留 | 保留，不用 label 代替 |
| 规则语言、版本、分类、执行环境和失败约定 | 保留 | 保留 |
| `rule_definition.script_source` | 完整返回已有值 | 省略正文；按下述标记补读 |
| stale 等影响业务解释的已有状态／warning | 保留 | 保留；不只剩 root_paths 而丢失失效状态 |
| 调试性匹配细节 | 沿用现有行为 | 继续精简 |

增加可选行级 `projection: {omitted_fields: [...]}`，只列当前可见内容因投影被省略的字段路径。
例如关联资源省略正文时列 `data.rule_definition.script_source`；没有正文则不产生省略标记。
Consumer 用该行 IRI 在同一获准 scope 请求 full 或既有资源详情，补读失败不能当作正文为空。

原始注解 literal 仍可能作为 fact 行进入上下文。full 可保留完整原值；compact 对含正文的
`ruleDefinition` fact 保留其 statement 身份、subject、predicate、object 类型信息，省略
`data.object` 并在 `projection.omitted_fields` 声明；不把删减后的 JSON 冒充原始 object。
可从 subject IRI 补读完整定义。这样仅 fact 输出也不会悄悄丢失该行或改变页集合。
已有其他任意业务 literal 不做脚本识别／自然语言删改；模型作者复制脚本的语义与保护责任
沿用 005，不能宣称 compact 是通用敏感信息脱敏器。

注解按现有单值写入合同解析；直接 RDF 写入导致无效 JSON 或多值歧义时保留可获准原始
statement，并给出通用可定位的注解读取诊断，不拼造“已确认”的结构化定义，不执行内容。
诊断只基于已获准值，不能从无权注解中产生提示。

## 4. 关联展开与分页算法

### 4.1 数据流

1. 解析服务端主体和 Project／Ontology scope，取得当前 `SemanticAccessView` 和技术版本。
2. 沿现有召回器取得候选，补取角色／注解，按完整值授权，再应用主命中筛选及既有融合顺序。
3. 选定当前匹配页。资源根用资源 IRI；statement 根使用其 subject 及 IRI object 作为邻接
   起点，不能误把 statement 的 `iri`（当前为 predicate）当作业务对象根。predicate
   本身的说明可按明确身份读取，但不以它连接所有使用同谓词的对象。
4. 在选定断言图中按确定顺序执行双向 BFS；每条候选先做完整授权，再进入结果或 frontier。
   scope、节点／quad 身份和已访问集合保证有界且不重复。跨 Ontology 通过真实 IRI 引用连接。
5. 为访问到的资源读取其自身说明／注解，并沿现有专属读路径取得 mapping、metric、Operation
   的已有结构；附着注解不算额外业务关系跳数。只有关系指向的实体才成为下一跳，JSON
   中的字符串不自动变成待遍历 IRI。业务映射引用仍由已知结构化字段或实际 RDF 边给出。
6. 合并已有 Shape／Operation 生产器与图邻域的结果，应用输出过滤、身份去重、root_paths
   和既有优先顺序；最后才按 `context_limit` 和 resume key 切页及投影。

资源 hydration 可以批量读取，复用现有模板／解析函数的字段约定；不通过循环内部 HTTP
请求搭建另一个服务层。资源自身注解也须授权：完整注解包含无权引用时，对应资源投影不能
通过先删字段逃过 `filter_candidate`。遍历边、源节点、目标节点和描述均按同一规则检查。

当前模板为 Operation 屏蔽内部实现字段，继续保留这个边界。业务节点指向 Operation 的
明确引用仍可召回 Operation 资源，再走既有结构化投影；不能通过移除所有模板过滤器暴露
操作内部 RDF。数据映射同样复用既有 mapping／metric 投影，不从表名推断业务边。

### 4.2 内部预算与可继续分页

采用“先枚举有界可见上下文，再排序切页”，复用现有无状态重算和签名游标，不新增服务器
会话缓存、图快照表或通用图查询框架。

- 页大小只控制返回行数。内部展开预算先取 **5000 个去重后的可见工作项**，用于当前主命中
  页的全部生产器；工作项指扫描并接受的语义 statement 或已读取的资源描述项，输出类型
  过滤前计数，因此只请求 fact 也不会无限扫描关系。相同项被多个根访问只计一次。
  此初始预算复用当前邻域查询已有的 5000 量级，不引入动态预算平台；通过能力发现公开。
- 各生产器不能再以 `context_limit` 为枚举上限；用稳定键分块读取后继续，直到候选耗尽或
  共同预算用完。分块仅是存储读取方式，不对外报告原始块数或被过滤数量。
- 原始 RDF 查询 LIMIT、重复标签行或受限内容不能消耗可见预算。原始块满时继续稳定键读取，
  先授权／去重再计数；补读直到下一条可见工作项或真实耗尽，才能判断是否 partial。
  使用包含 graph、s、p、o 类型／datatype／language 的稳定键，不能用 label 作续读键。
- 有预算时按根的既有顺序、距离和稳定身份枚举；只要 scope、版本、查询、匹配页与授权相同，
  同一上下文候选集合与 `context_limit` 无关。排序后只对枚举出的可见集合切页。
- 预算用尽而仍存在下一可见项时，`expansion.status=partial`；已枚举的集合仍可分页。
  最后一页允许无游标但保持 partial，不能发一个无法取得新结果的虚假游标。
  Consumer 可缩小范围、减少主命中，或以已返回 IRI 开始新的有界查询；本期不保证任意
  大邻域一次查询链都能穷尽。
- 存储超时／错误沿既有错误合同返回，不伪装完整或根据被隐藏数据量生成特定 partial 告警。
  不放宽授权，也不把读取错误终止为整个建模 run 不可修复；调用方可修正范围后重试。

根数与匹配页变化会改变一次展开的范围，属于不同请求；“小页与大页最终集合相同”针对
同一主命中页、同一预算未耗尽的 `context_limit` 对照，不承诺不同主命中预算得出相同结果。

### 4.3 完整性合同

保留现有 `matches_page`、`context_page`、顶层 `truncated` 及 `recall`；增加
`context_page.expansion` 与固定范围声明 `query.result_scope`。以下为拟新增字段示意，
不是当前已实现的响应：

```json
{
  "query": {
    "result_scope": "authorized_query_scope",
    "semantic_roles": ["action"],
    "depth": 2
  },
  "context_page": {
    "returned": 3,
    "truncated": false,
    "next_context_cursor": null,
    "expansion": {
      "status": "partial",
      "reason": "expansion_budget_reached"
    }
  }
}
```

| 信号 | 准确含义 |
| --- | --- |
| `recall.completeness` | 既有主命中召回／索引状态，不扩成业务语义完整性 |
| `context_page.truncated`／cursor | 已枚举的可见上下文是否还有下一页 |
| `expansion.status=complete` | 当前主命中页、scope、assertion 选择、depth 和可见图内的有界展开已耗尽；不保证全图或业务完整 |
| `expansion.status=partial` | 内部展开预算使该邻域尚未枚举完；reason 为 `expansion_budget_reached`，不含隐藏资源原因 |
| `expansion.status=not_requested` | depth=0 或 context_limit=0；reason 分别为 `depth_zero` 或 `context_disabled`，同时为零时采用 `context_disabled` |
| 主命中为空且请求了展开 | 空集合内 complete；`result_status=no_match` 沿用，仍不能推出业务定义不存在 |
| `query.result_scope` | 所有成功响应固定为 `authorized_query_scope`，不随隐藏关联存在与否改变 |
| `projection.omitted_fields` | 可见字段因投影被省略；不代表未建模或无权 |
| 注解 unknowns／conflicting_meanings | 已披露业务信息状态，不由检索是否命中自动生成 |

顶层 `truncated` 继续等于两个 page.truncated 的 OR，避免改写既有字段含义。
partial 时另加通用 `context_expansion_incomplete` warning，并更新 Consumer／检索完成
检查读取 expansion，防止旧逻辑只看顶层 truncated 就误判完整。新增状态不是建模 run 的
不可恢复硬门；只能限制对应“已完整读回”的声明，允许补读后继续。

## 5. 授权、版本与失败处理

本条不采用“受限规则占位”或 `missing_due_to_permission`：它们会违反已冻结的不可区分
合同。公共流程可读并不使它引用的受限规则可读；隐藏相应边，不返回名称、阈值、隐藏个数
或依隐藏内容变化的 partial。统一范围声明足以提醒 Consumer 不作封闭世界推断。

身份／权限在每次请求重新解析；`semantic_roles` 规范化后的值加入 cursor binding。
继续允许同一结果切换 full／compact，因为投影不改变分页集合，不需要为视图切换创建
新查询身份。原始 query、既有过滤／预算及图／源版本继续按现有合同绑定。

Grant 变化已有主体绑定；保护集成员变化也可能改变可见集合而不改变 RDF／Grant 字符串。
续页因此增加当前查询**可见候选及展开集合**的摘要校验：只使用获准结果的稳定身份与内容、
已获准遍历边和展开状态，不使用隐藏成员清单、被拒数量或保护集全局版本。这个摘要复用
查询本来就枚举的集合，不扫描整个 Project；主命中游标覆盖主命中候选集合，上下文游标
同时覆盖当前匹配页的展开集合。可见集合变化时按既有 `context_snapshot_changed` 重查。
隐藏集合变化且可见结果不变不得单独使摘要不同。

在输出之前复核已绑定的图／派生源版本；变化则返回现有快照错误，不组合变更前的主命中和
变更后的注解。先比较 query／principal 等静态绑定，再校验可见快照摘要，错误不包含原始
受限 IRI 或授权原因。无需为了临时 cursor 的格式变化支持历史数据库迁移。

| 情况 | 处理 |
| --- | --- |
| 新筛选参数错误 | 沿 REST／MCP 既有参数校验方式反馈字段位置，不新增流程硬拒绝 |
| 精确 IRI 无权／不存在／角色不匹配 | 统一正常 no_match 形状；不说明是哪一种 |
| cursor 篡改／请求不匹配／快照变化 | 沿 `invalid_context_cursor`／`context_cursor_mismatch`／`context_snapshot_changed` 合同 |
| 角色／脚本／业务信息未声明 | 保留缺失或已存未知；不生成规则或默认执行许可 |
| 说明与脚本已有冲突声明 | 原样返回并由 Consumer 判断不足；不静默选择脚本或文字 |
| 授权依赖故障或 RDF 读取失败 | 失败关闭且返回实际通用错误，不返回伪完整空结果；允许同目标重试 |

不同请求补读后，Consumer 应比较返回 scope 的 workspace／source 版本；漂移时重新读取
受影响部分。版本一致只证明读取基线一致，不能证明脚本说明一致、引用兼容或业务完整。
007 的私有 review 不是 Consumer 数据源；只有已获准物化的业务说明／未知／冲突可读。

## 6. 实施触点与相邻交接

以下列出后续实施的最小职责分配，不是本轮开发授权。

| 文件／合同 | 计划改动 | 对应验收 |
| --- | --- | --- |
| [`api/schemas.py`](../../../backend/app/api/schemas.py)、REST／MCP semantic 入口 | 新筛选透传与验证；同服务返回合同 | A1、A7、A9 |
| `semantic_context_query.py` | 注解 hydration、角色筛选、资源／statement 身份、投影、授权后 BFS、生产器预算分离与 expansion | A1—A6、A8 |
| `semantic_sparql_templates.py`、必要时 `semantic_read_model.py` | 复用描述／注解模板；稳定分块邻接及通用关联读回；避免另建业务专用模板 | A2—A6、A8 |
| `semantic_access.py` | 优先复用完整值／嵌套 IRI 过滤；仅在新增投影确有未覆盖字段时局部补齐 | A5、A7 |
| `semantic_context_cursor.py`、`semantic_context_capabilities.py` | 角色筛选及可见集合绑定；公开状态、投影、预算约定 | A6、A7、A9 |
| [`REST 合同`](../../reference/api.md)、[`MCP 合同`](../../reference/mcp.md) | 同步新参数、scope 声明、full／compact 及分页／展开区别 | A9 |
| [`protocol_retrieval_gate.py`](../../../modeling_team/protocol_retrieval_gate.py) 及实际活动 Consumer／Examiner 工具适配 | 新参数冻结／透传；明确 partial 不证明完整；提供补读路径，不加 Agent 数量／角色硬门 | A9；A10 留待授权 |

实际工具若通过额外代理收紧参数，需要沿真实调用入口机械对齐，不能只修改 MCP 函数签名。
旧历史任务／验收记录不追改。无需新页面；若后续实施确实修改前端代码，才按仓库规则执行
前端验证。关系／注解写入合同由已交付需求拥有，本条不重写 Batch、候选或场景地图。

数据／接口映射后续按 010／011 的真实字段机械接入现有资源投影与通用显式引用；不重新打开
本条的身份、授权、分页和不执行外部系统的决定。若它们引入新的业务范围，回到其权威需求
处理，不能用“机械对齐”暗含业务设计授权。

## 7. 验证、完成边界与检查记录

验收逐项遵循需求 A1—A10，不新建只服务本次输出的一次性验收框架。优先扩展现有
[`Context Query 测试`](../../../backend/tests/test_semantic_context_query.py)、
[`API 测试`](../../../backend/tests/test_semantic_context_query_api.py)、
[`MCP 测试`](../../../backend/tests/test_semantic_context_query_mcp.py)、
[`cursor 测试`](../../../backend/tests/test_semantic_context_cursor.py)及既有授权测试。

重点反例：单个邻域超过一页但只有一个 producer；重复 label、不同 IRI；同 Action 不同调用；
受限节点两端均公开；脚本 JSON 内嵌受限 IRI；compact 的原始 literal 旁路；depth 之外仍有
关系；预算正好耗尽与确有下一项；仅 fact 输出跨过关系；图未变但保护成员变化；隐藏集合
变化但可见结果不变。至少再用一个不含工单概念的 fixture 证明生产代码没有领域分支。

后续开发需执行仓库规定的 backend 全量 pytest，适用时执行 Modeling Team 合同测试；
完成后按仓库规则重启服务并检查 health／受影响查询入口。开发验证、独立功能验收与 A10
真实独立语义验收分别记录，不能由本设计自查代替。A10 跟随用户统一授权，无当前运行额度。

本轮文档自查记录：完成需求 F1—F6、D1—D8、A1—A10 与设计对应核对；检查本次文档的
88 个本地链接／锚点、Markdown 围栏／表格、1 个 JSON 示例和条款编号，均未发现错误；
`git diff --check` 通过。D1—D8 无待用户决定项。该记录只证明文档内部一致性；
未运行产品测试、未重启服务、未执行独立审阅或语义验收。
