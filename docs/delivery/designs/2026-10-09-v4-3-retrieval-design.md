# v4.3 剩余检索增量设计

范围：[R4.3-008—012](../../requirements/requirements-v4.3.md)。用户已授权实现；Jev
验证初始按要求等待 key，同日提供 OpenCode key 后恢复，但推理实测 HTTP 451，
见[后续记录](../records/2026-10-09-v4-3-retrieval-delivery-record.md#jev-验证恢复与外部阻塞)。
真实建模、Consumer/Judge 语义运行仍暂停，不消耗额度。
本轮为工程交付，不追加正式流程或独立验收 Agent，不将开发验证写成独立验收。

- **008**：按现有三种注解的合同字段提取保存值，向量文档以字段路径和原文保存到现有
  descriptions 证据列，不添加事实、表行或数据库列。词面查询枚举作用域内注解资源、解析
  JSON 后匹配字段，兼容保存为 Unicode 转义的 JSON；完整资源授权后才计额。
  投影与模板升级到 v2，旧版本降级，沿既有 coordinator 重建，不推进模型修订。
- **009**：`full/compact` 保持；`preview` 主命中完整，`related_context` 为唯一摘要注册表，
  每个根的 `neighbors.preview_ref` 以零基数组下标引用当前 `related_context` 周边页；
  稳定 `(ontology_id,kind,id)` 只在对应摘要中保存一次。
  名称、IRI、类型、声明角色及最长 160 字原文摘录留在摘要，完整注解/Mapping/参数不返回。
  原始 JSON literal 不绕行带回正文，保留其 statement 身份、谓词、datatype 和详情入口。
  `preview/details_omitted/truncated` 区分省略；省略不是未知或模型缺失。
  `context_page.returned` 只计去重摘要，每页全局限额，neighbors 引用不另计额、不另分预算。
  续页主命中定义不变，neighbors 对应当前页，客户端可按稳定身份累计。关系/事实可区分；
  relationship 及资源的直接关系摘要保留 subject/predicate/object，neighbors 的方向相对根；
  `relationships.index` 定位该摘要的关系项。多跳只声明距离，不能冒充根的直接关系；
  完整中间路径继续通过实际 statement/分页读取。根带 Ontology 身份，重名资源不合并；preview 的 root_paths 用 `root_index` 引用当前
  primary_matches，关系项也沿此方式绑定。页内下标不作为跨页资源身份。
  摘要引用和关系元数据有固定额外成本，短定义不保证缩小响应；长定义及共享邻居应实测。
- **010**：同步旧单题 prompt、Skill 及连续批次 prompt；按信息缺口继续、充分即回答、
  无价值重复换方向或提交未解决项，不用次数判断缺失；会话截止和用户控制保留。
  实际代理默认 5 个主命中、全局 20 周边、深度 1、preview（精确 IRI 同样配置），
  显式配置保留；schema 允许更大周边页，默认不是完成门。
- **011**：完整表达式等于标签/别名才为精确；仅拆分词项相等用 `*_term_equal` 及较低
  分数，包含匹配保留其他依据。默认版本 `exact-expression-max-v2` 保留 max 融合与
  同分支持裁决，修复错误的精确等级。新增 `evidence-rrf-v2` 待验证方案，按授权去重
  候选的词面/向量 rank 进行 RRF（offset=60），不同表达式累加支持，完全重复表达式不加分。
  精确依据仍优先，候选不因低分剔除；rank_score 与旧 score 分开声明。受治理原始完整
  语义参加召回与词面评分，展示预览不作评分输入。
  固定候选对照工具比较 Recall@5/10、nDCG、必要关系入口、缺召回与耗时。其 relevance
  为业务提供的 0—3 等级（1 含必要背景），不是 confidence。已保留共同命中造成排序退步
  的控制样本，故 RRF 不默认启用。真实公开题/中文/跨语言/Consumer 效果待证；初始 Jev
  等待 key，恢复后 API 请求未取得评分，仍未选型或接入生产，不能先接 API 宣称质量通过。
- **012**：仅缓存查询向量，精确文本、完整检索配置哈希和凭据身份隔离，进程内最多 256
  项、TTL 300 秒，返回副本，不存候选/授权/邻域快照。外部错误不缓存；自定义 client
  保持自身策略。每次查询重新授权、检查 scope/revision/index/cursor。
  邻接缓存只在一次请求中，批量读取未见节点并按端点复用；只有完整枚举才保存，
  预算中止不缓存半页。路径、方向、距离、每根访问集和可见预算仍分别处理。

影响：Context 服务/词面模板/向量投影、REST/MCP schema、Team 读取代理与 Consumer
提示。无数据库迁移、前端变化、Jev client 或业务专用分支。GitNexus MCP 不可用，本次
采用调用点/差异/合同回归检查，无图影响覆盖主张。
