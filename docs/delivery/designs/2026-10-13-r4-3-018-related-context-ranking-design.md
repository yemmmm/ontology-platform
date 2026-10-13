# R4.3-018 周边上下文回答相关度排序设计

日期：2026-10-13。权威范围：[R4.3-018](../../requirements/requirements-v4.3.md#r43-018-related_context-按回答相关度排序)。
设计阶段静态代码基线：`e3bc80c`。独立设计 Round 1 PASS。
设计阶段授权为细化、设计及独立审阅；后续同日用户授权按设计实现及测试。
当前工程已实现，独立工程 Round 4 PASS；后端全量和重启入口验证通过，见
[交付记录](../records/2026-10-13-r4-3-018-delivery-record.md)。不调用外部 Jev，不恢复建模或业务验收。
决策主记录为需求的 D1—D8。本文件描述拟实施合同；下述字段和示例均不是当前功能证据。

## 1. 问题、范围与最小方案

查询“关闭工单需要满足哪些条件”，一跳普通背景可能排在第三跳的关闭条件之前。
本条对当前主命中页已经取得、授权合格、输出筛选合格的周边集合去重后评分，再整体排序、
冻结并分页。第三跳条件可排在一跳背景之前，桥梁和连边依然留在集合中；数组顺序不表示
连接顺序。源中的明确未知同样可以具有回答价值，相关分数不证明事实正确。

自然语言默认 `context_order=relevance`，调用者可显式选 `graph_distance` 取得原排序。
两种顺序独立于 `expansion_strategy=adaptive|fixed`，不改变主命中及候选扩展、深度、
类型筛选或保留规则。单个精确 IRI 没有自然语言问题，实际顺序固定为 graph_distance，
不调用周边评分；不新增 original_question 或另一路由。暂不修改前端及 Consumer 默认配置。

不采用按根分排、按每页评分或继承 adaptive 的最高回答分数：前两者不能实现当前根页
有界集合的全局排序，后者的评分对象及到达上下文不同。直接复用 adaptive 探索分数也会
把导航价值冒充直接回答价值。只复用量表、HTTP client、容量控制、快照与授权核验。
不新建存储表、评分框架、业务规则、资源路由、图闭包扫描或重试机制。

## 2. 实际基线与复用位置

以下为静态阅读事实，不是运行验证。

| 实际入口 | 已有行为 | 最小增量 |
| --- | --- | --- |
| [semantic_context_query.py](../../../backend/app/services/semantic_context_query.py) 的 `query_multi` | 先主命中召回／Jev 重排，再 adaptive 或 fixed 扩展，最后 context 截页 | 在扩展完成与 context 截页之间调用一次周边排序；独立记录周边排序状态 |
| 同文件 `_expand_multi_primary`、`_context_sort_key` | fixed 多根合并；按距离、来源、kind、Ontology 顺序、名称、ID 排序 | 原键保留，relevance 同分时直接复用；保留已读路径材料供评分 |
| [semantic_context_adaptive.py](../../../backend/app/services/semantic_context_adaptive.py) 的 `AdaptiveContextExpansion.run`、`selected_paths` | 选择、连接保留、各根最短距离；分支分数存在 `expansion.score_contexts` | 向最终排序传递已读完整资源／边和规范路径，不改变选择决策 |
| `_hydrate_candidates`、`_resource_from_rows`、`_neighborhood_chunks` | 完整定义 hydration、请求缓存、授权后的实际资源／边 | 评分前复用完整值；已有读取中记录必要中间材料，不能只用 projection 摘录 |
| [semantic_jev.py](../../../backend/app/services/semantic_jev.py) 的 `JevReranker.score_branches` | 独立候选问题、完整输入、30 KB／60 KB 容量、分批、部分成功、模型一致性 | 增加具体 `score_context` 入口及周边专用问题构造；复用内部传输／标量校验，本条消费层采用整集合降级 |
| `query_multi`、`_resume_adaptive_context` | adaptive 已保存完整选中周边；fixed 尚重做扩展 | 共用 context 快照保存已排周边、分数、排序状态；fixed relevance 续页也直接恢复 |
| `_cached_access_unchanged`、`_verify_scope_snapshot`、`_verify_access_snapshot` | 保存旧授权视图，实际可见源差异核验及输出前核验 | 复用到 fixed relevance 和其根排序缓存；不复制旧 fixed 的完整无权集合缓存键 |
| [semantic_context_cursor.py](../../../backend/app/services/semantic_context_cursor.py) | cursor v4、签名、请求绑定、context_snapshot_id、稳定恢复键 | 绑定顺序／排序配置；升级 v5，使部署前 cursor 明确重新首查 |
| `_multi_response`、`_preview_related_row` | preview 去掉 match；compact 当前保留 match；neighbors 用页内下标 | 周边相关度独立 envelope，三种投影均保留；先排页再生成 preview_ref |
| [REST schema](../../../backend/app/api/schemas.py)、[REST handler](../../../backend/app/api/semantic.py)、[MCP](../../../backend/app/mcp/tools/semantic.py)、[能力发现](../../../backend/app/services/semantic_context_capabilities.py) | 同一服务；REST full，MCP compact | 增加 context_order、有效顺序与能力说明；同步 API/MCP 文档 |

当前 fixed full／compact 的 root_paths 只带 root_match_id，而 preview 带 root_ontology_id。
排序内部始终使用 `(root_ontology_id,root_kind,root_match_id)`，不按裸 IRI／数组位置合根；
公开 full／compact 的 root_paths 可加 root_ontology_id 以消除同 IRI 根歧义，既有字段保留。
稳定周边身份沿用 `(ontology_id,kind,id)`，资源、statement 和 derived_reference 不按名称合并。

## 3. 请求、有效顺序与评分输入

新增 `context_order: Literal["relevance","graph_distance"] = "relevance"`，REST 和 MCP 一致。
query.context_order 回显请求解析后的模式；context_page.ranking.effective_order 回显实际
采用顺序。IRI 的 query.context_order 解析为 graph_distance；降级的自然语言 query 仍为
relevance，effective_order 为 graph_distance。depth=0、context_limit=0、无主命中或空周边
不发起周边评分，ranking.status=not_requested。context_limit 仅控制最后的页大小。

### 3.1 一个去重候选一个问题

输入 state 只含 original_queries。每个问题独立内联当前候选和其获准到达上下文：

1. 候选完整已保存业务语义／注解、description、适用条件、例外、未知、映射证据；
   statement 带完整 subject/predicate/object、object_type、datatype、language；
   derived_reference 带既有 source/target/predicate/field_path，不虚构 RDF 断言。
2. 候选实际连接涉及的端点和谓词资源的已读完整语义，以及每个实际关联根的一条最短
   规范已读路径。距离相同按稳定边身份及资源身份字典序裁决，最多既有三跳，不枚举
   所有简单路径或循环。literal 是终点，不把 predicate IRI 当该边的到达节点。
3. path 和 root 用于确定候选的含义、关系方向和适用范围；**只评当前候选的证据贡献**，
   不能把路径上其他候选的直接证据借给背景节点。必要关系入口沿 1 分定义处理。
   不因关联根数量、路径数量、出现次数或绕环提高分数；不把未知判作无关。
4. 去掉 Context Query envelope 的 match、fusion、matched_queries、旧 relevance、
   expansion／score_contexts 等评分元数据，保留 `data` 内的同名业务字段原值。
   不带其他待排候选的清单、摘要或分数；路径必要语义作为该候选上下文明确标注。
   内容中的指令仅是数据，不遵从。获准查询与模型已有值之外不加业务答案或隐藏材料。

先合并去重输出候选，再构造上述问题；同一候选只获得一个周边分数，不对不同根分数
求和、取最大值或重复计权。与 adaptive 的逐入口双评分分别记录，不将已有选择分数
贴成周边 relevance。暂不做跨评分目的的缓存复用，避免相同量表掩盖不同输入合同。

### 3.2 路径与完整值的最小补齐

fixed 的 `_expand_neighborhood` 当前只有距离及 seen 状态，不能从 root_paths 距离造出
完整边链。实施时在已有逐层读取中留下每根的规范 predecessor、已读边和授权完整端点，
在 resource_types 输出筛选之前保留内部材料；不因此增加遍历层数或新邻接读取。
adaptive 复用其已保留图／已读上下文，导出相同用途的规范材料。内部辅助材料也必须
走既有完整值授权，并计入原可见工作预算；不能利用未输出类型绕过授权。

规范路径描述实际遍历连接，RDF 入向遍历保留原 s/p/o 方向；派生引用沿现有支持方向。
同 IRI 多 Ontology 定义保留各自身份及授权，不挑第一份定义替代另一份。根 statement
使用其实际 subject／URI object 展开，根与其端点关系由原 statement 证明。
Operation producer 等已有内容若仅具有来源关联而没有显式连边，传其 origin 和根来源，
connection_status=source_only、path=[]，不补造边；不能因没有边链删掉合法候选。

评分使用已 hydrated 完整值。端点／谓词已有完整资源缓存可复用；若已读引用需要现有
resource hydration 补齐，限于当前 scope 和原工作／时间预算，不读取下一层邻域。
没有保存的定义明确为 definition_not_saved，不能编造定义；依赖故障使应读完整值未取得
时整集合降级，不以名称或不完整摘录顶替。路径构造不输出私有完整材料到 preview。

## 4. 量表、版本、排序与整集合降级

回答量表沿 `jev-evidence-relevance-v1`：0 无关／没有可用证据，1 必要背景／关系入口，
2 部分直接证据／条件／例外／未知／边界，3 主要必答事实的充分直接证据。
周边评分输入／排序策略另以 `related-context-relevance-v1` 版本化；量表语义不改。
模型实际 ID 来自既有响应头或 payload 的校验，不以配置别名冒充实际版本。

`score_context` 是具体适配入口，复用 score_branches 的分批传输和校验；为周边构造
answer-only 问题（can_explore=false），采用 §3 的专用说明、版本及 envelope 清理。
只为两个实际入口共享的代码作局部提取，不创建通用评分插件。

正常流程：

1. 有界输出集合 C 已冻结内容及来源，沿原键取得基线顺序 B。
2. 每个去重候选一次评分，finite 0—3，布尔、NaN、越界、缺项／重复映射均无效。
   全批次及主命中／adaptive 已成功评分的实际模型须一致；将已有实际模型传入
   expected_model。已有成功阶段模型互相不一致时不得继续周边评分或拼接其分数。
   没有先前成功模型时首个成功批次绑定，后续批次必须一致。
3. 全集合成功才用 `(-relevance_score, 原_context_sort_key)` 排序。没有主命中的
   “完整表达式精确匹配优先”例外；不调用 apply_jev_ranking 的主命中过滤／优先逻辑。
4. 评分后的稳定身份集合、完整业务值、root_paths 和既有 expansion 保留信息与 C 一致。
   0 分候选也保留；过滤只沿原授权／类型／探索规则，不新增 0.5 或其他周边阈值。
5. 任何一个候选未能完整评分时，整集合使用 B，所有周边 relevance_score=null、
   relevance_status=unavailable；本条不发布成功批次的局部排名，不把未知记为 0。
   最先失败的安全 reason、candidate_count、完整成功数量与耗时记录在 ranking；
   评分器内部先前成功不丢历史，但不改变当前公开排序／资格。

全体回退比“成功者排前、未知排后”更保守，但避免把未评候选当低相关，且明确满足
登记的失败沿原排序。超大单候选不删条件／例外来硬凑评分；预算不足不只评第一页。
本条不因评分故障让正常受治理读取永久失败。源修订、授权、快照核验失败仍沿原错误，
不能用降级输出不合格值。

### 4.1 工程初始预算

| 项目 | 初值及用法 |
| --- | --- |
| 输出集合 | 复用原累计最多 5000 个授权可见工作项；不为排序少读、删候选或扩图 |
| 周边评分候选 | 每根页最多 512 个去重候选，独立于 adaptive 已用的分支上下文计数；超过上限整集合降级为 candidate_budget_reached，不评分前 512 再丢其余 |
| 单问题／批次 | 复用 30000／60000 UTF-8 字节合同；包括完整查询及实际序列化输入，不截必要值 |
| Jev 时间 | 主命中、adaptive 分支、周边排序共享本请求剩余 semantic_jev_timeout_seconds，默认 15 秒，不为本条新增 15 秒或按批次重置 |
| 周边排序截止 | 从 query_multi 入口计 30 秒软截止，使用 min(剩余 Jev 时间, 剩余截止)；fixed 的既有邻域读取不被本条改成新的硬截止 |
| 快照 | 复用总共 64 项／默认 600 秒 TTL；包含降级集合，根快照与周边快照共用容量 |

cached 根评分在当前请求不再花时间，match 新页可使用当前请求额度；仍绑定原实际模型。
context 续页不评分、不追加预算。缓存键需加入 timeout／上述排序配置／prompt 摘要，
不同预算不能复用先前降级排名。15 秒通常还剩多少、512 覆盖多少均待实测，不能承诺
默认 relevance 必然应用。时间耗尽整集合降级，已取得第一跳、路径及深层结果保留。

ranking.reason 使用安全类型：scoring_disabled、candidate_budget_reached、
candidate_exceeds_context、timeout、invalid_response、model_changed、hydration_unavailable。
统一映射既有错误；原始 HTTP 正文、凭据、无权资源及隐藏数量不进入公开字段。

## 5. 输出合同与投影

周边项增加独立 `relevance` 对象，沿主命中已有 relevance_* 名称和含义。
不把它放入 match，因 preview 去掉 match；不改变旧 score、confidence 或主命中 relevance。

```json
{
  "query": {"context_order": "relevance"},
  "related_context": [
    {
      "ontology_id": "ontology-example",
      "kind": "fact",
      "id": "statement-example",
      "relevance": {
        "relevance_score": 2.8,
        "relevance_scale": [0, 3],
        "relevance_model": "actual-upstream-model",
        "relevance_version": "jev-evidence-relevance-v1",
        "relevance_status": "scored"
      }
    }
  ],
  "context_page": {
    "ranking": {
      "requested_order": "relevance",
      "effective_order": "relevance",
      "status": "applied",
      "version": "related-context-relevance-v1",
      "score_version": "jev-evidence-relevance-v1",
      "score_scale": [0, 3],
      "model": "actual-upstream-model",
      "reason": null,
      "candidate_count": 12,
      "scored_count": 12,
      "filtered_count": 0,
      "ranking_scope": "current_match_page_bounded_context",
      "snapshot_reused": false
    }
  }
}
```

示例为局部结构，省略真实行中的 data／root_paths 及原分页字段，不代表可直接调用。

| 状态 | score／model 与有效顺序 |
| --- | --- |
| applied | 所有项 scored，真实分数／实际模型；effective_order=relevance |
| degraded | 所有项 unavailable、score=null、model=null；effective_order=graph_distance，带安全 reason 和 context_ranking_degraded warning |
| not_requested | graph_distance 显式请求或 IRI、空集合／不展开；score=null、status=not_requested、model=null，不发降级 warning |

relevance_version／scale 在 unavailable／not_requested 仍明确量表，不能将 null 解释为 0。
ranking.scored_count 为本次完整校验成功的实际数量；degraded 时这些数值不公开为行相关度，
不表示已应用局部排序。filtered_count 恒 0，仅指本条增量，无权数量不进入该统计。
expansion.status／selection_status 与 ranking.status 独立：探索 partial 可在已得有界集合
上排序成功；探索 complete 也可排序 degraded。排序 applied 不证明全邻域或业务完整。

`_public_item`、compact 和 preview 显式保留 relevance；preview 不带完整评分输入、
路径全文或候选语义，仍保持短摘录与实际连边字段。neighbors 在排序、截页、投影之后
按当页 related_context 数组生成 preview_ref，不保留重排前下标。
关系本身独立评分，不复制端点分数。root_paths／真实关系／expansion 的 path_projection
和 next_context_cursor 保留；路径跨页为 paged，类型省略沿 filtered，源读取未完沿 partial。
一页有直接事实而桥梁在后页不补造连通图，续页仍可取得全部冻结桥梁／边。

## 6. 快照、授权与双分页

把 `_resume_adaptive_context` 所做的冻结周边恢复收敛为适用于“adaptive 或 relevance”
的具体恢复路径。adaptive graph_distance 沿已有快照，fixed graph_distance 沿原确定性
流程；fixed relevance 无论 applied／degraded／scoring_disabled 都保存完整周边快照，
不以主命中 Jev 成功／启用为前提。

首次自然语言请求流程：

1. 主命中召回／排序及根页解析仍沿原合同。需要周边快照的 fixed relevance，根缓存也
   使用已有服务端 access_view 和 `_cached_access_unchanged` 核验，采用 adaptive 的
   缓存定位方式，不再以完整无权集合变更公开失效。
2. 原扩展返回 C 和内部获准路径材料，按 §4 取得已排集合，保存完整行、root_paths、
   expansion、周边 ranking／分数、根排序状态、根页恢复信息、索引与旧授权视图。
   只保存输出／恢复必需材料，评分全文辅助输入不另存一份公共数组。
3. context key 包含原请求 binding、根排序快照身份（若有）、当前根页起点／root digest、
   context_order 和排序配置摘要。binding 加入顺序和配置 digest；排序后的内容／分数／
   实际模型／状态／路径进入 context_digest，不只验证“ID 集合没变”。
4. 检查当前 scope／授权后保存，再截 context_limit；生成引用该 context_snapshot_id
   的 cursor。降级集合同样冻结，服务恢复不能让下一页重新排名。

续页先核验原签名和请求绑定、当前主体／scope／源修订／索引／配置，取 context 快照，
用既有旧／当前私有授权视图对照。检出新增可见或撤权时返回 409 context_snapshot_changed；
纯隐藏内容的变化在实际可见源未变时不暴露失效信号。核验依赖失败按原 dependency_error
返回可重试，不能重排或从旧缓存泄露值。反例必须包含“移出最后保护集而 revision 不变”。
核验涉及必要实际源读取时不称为重复扩展；禁止重新召回、生成向量、扩图、Jev 评分。
无 cursor 重复首查复用前同样核验；不能只重验旧集合而漏掉新可见内容。

周边快照引用根排序快照时，两者都须有效；即使没有根排序快照也由周边快照恢复原根页。
过期／淘汰／重启／配置变化返回原 snapshot_changed，不自动新评分修补旧 cursor。
固定签名 secret 不使进程内快照跨重启存活。cursor 升为 v5，旧 v4 明确 invalid_context_cursor
并提示无 cursor 首查；不增加旧 cursor 兼容层。

在已排数组中按现有稳定 `(ontology_id,kind,id)` resume_key 找到边界，不能用距离排序键
推算下一页。cursor 绑定 page size 及投影沿原合同，改这些参数须首查。snapshot_reused
仅为运行元数据，不改变业务排名／context_digest；沿既有响应重放投影排除缓存命中标志，
本条新增字段须同步重放归一化，避免再次把缓存状态变化判作语义 drift。
本次记录原首次评分耗时和候选数，续页不把它们归零伪造成本收益。

match 下一页是新根页：原主命中排序保持，首次建立该页周边快照及排名，当前页不声称
优于其他根页／未探索候选。跨根页共享资源仍可再次返回，以保留来源，不用全局去重删后页。

## 7. 实施交接、验收与效果边界

后续实现的最小顺序：评分输入／量表与降级 → 两种扩展共同的排序接入 → fixed relevance
快照及 binding／v5 cursor → REST/MCP／能力发现／三种投影 → 重放归一化与使用说明。
拟变更文件以 §2 为主，另包括 `modeling_team/__main__.py::_cq_mask_reissued_ranking_cache_hit` 的缓存元数据
归一化实际入口，只同步此字段，不扩大验收运行框架。
开发前按 AGENTS.md 做实际公共合同影响分析；本轮仅文档，不做符号变更或图覆盖宣称。

复用现有 `test_semantic_jev.py` 的 HTTP stub、`test_r4008_context_query.py` 的 DatasetStore、
`test_r4317_adaptive_context.py`、API/MCP／cursor 测试及
已有响应重放测试。依据需求 A1—A9 补真实行为反例，禁止只 mock 一个 sorted 结果证明流程。
后续开发须按仓库执行 backend 全量 pytest、受影响 Team 测试、重启与受影响实际端点；
独立工程测试与最终业务语义验收分别记录。本轮不运行这些阶段，也不调用外部模型。

真实效果 A10 待后续授权：先冻结同修订、获准公开中文问题、同根页、相同 C／内容／
路径／预算，只比较 B 与 relevance 顺序；固定深度和 adaptive 各有对照，避免把扩图收益
误算排序收益。人工独立业务标注必要事实／条件／例外／未知及连接，不能让 Jev 分数
自证正确。然后沿已有 Consumer／Judge 路径检查端到端结果，分开披露召回／候选差异。

比较前 5／10／实际页大小中的有效证据、必要路径覆盖及具体退步、补读次数、响应及
总 token、评分／邻接／总耗时、降级比例；必要条件或未知丢失不得用平均分上升掩盖。
不预设提升百分比，没有改善如实记录；工程 PASS 和默认采用不推导检索质量 PASS。
完整业务效果和 120 分钟目标仍归原独立语义及性能合同，不缩小范围、不用隐藏题调优。

## 8. 自查、独立审阅与完成边界

需求 F1—F7、D1—D8、A1—A10 与设计已作一致性自查；10 个本地链接／锚点、
Markdown 围栏、JSON 示例和 diff 检查通过。需求文件只修改018的范围状态、总表及正文，
其他条目与初始阶段预算未改；无代码变更，无产品测试、外部评分、服务重启或真实建模。
这些检查只证明文档结构及范围，不证明工程行为或业务效果。

### 独立审阅 Round 1 — PASS

- 日期：2026-10-13；Reviewer 为独立 `plan_reviewer`，task `/root/r4318_design_review`。
- 静态代码基线：`e3bc80c`；需求输入 SHA-256：
  `1924b546737707f4c0d3cd92476be82f87c948fe10e73c4c5b82760cd655e57f`；设计输入 SHA-256：
  `e511d3b1c7b909afc64e0935d5796961f0cddc73ba32bb589ac0467f991a35fd`。
- Reviewer 实际确认输入摘要一致；结论 **PASS，0 Critical／0 High，无未决关键假设**。
- 完整覆盖018原登记与细化、009／011／012／017依赖、候选隔离和贡献、完整语义／
  真实路径补齐、多根身份／环、共享预算／模型一致性／整集合降级、fixed／adaptive
  快照、实际源授权变化、双分页／v5 cursor、三种投影／preview_ref及精准重放归一化。
- 独立依据：设计§3—4明确一候选一次、不借其他路径证据及无新增淘汰，实际读取入口为
  `semantic_context_query.py::_expand_neighborhood`；§4.1的有限预算及整集合消费策略可
  复用 `semantic_jev.py::JevReranker.score_branches` 批次校验；§5—6以现有
  `_cached_access_unchanged`／`_resume_adaptive_context`和 Team 精确重放归一化为基础，
  对固定深度所需增量明确，不从旧实现推导本条已交付。
- Reviewer 未修改文件、提交、运行测试、启动服务、调用评分或建模，未接触隐藏答案。
- 独立报告未提出必须修订的阻塞项。PASS后仅同步状态及本审阅记录，未改变需求的
  F1—F7／D1—D8／A1—A10或设计§1—7；无额外复审轮次。

设计已可交接后续实施；A1—A9工程行为和A10真实效果仍待相应授权及独立证据，
不以设计PASS恢复已暂停／撤销的运行或改变额度。
