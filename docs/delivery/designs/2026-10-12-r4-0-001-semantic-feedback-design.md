# R4.0-001 真实使用反馈与本体改进设计

## 1. 权威范围与交付状态

权威范围：[R4.0-001](../../requirements/requirements-v4.0.md#r40-001-基于真实使用反馈的本体持续改进)。
本轮用户授权需求细化与设计，确认独立反馈接口、召回页面反馈入口、外部 Agent 同合同接入，
并同意由通用增量建模能力承担后续模型修改。决策主表保留在权威需求 D1—D7。

基线为 2026-10-12 checkout 440d534。本文是实施交接设计；没有实施、独立设计审阅、
功能验收或真实业务效果结论，不授予新的建模次数、外部调用或部署权限。

例：query“返修工单的责任如何判断”返回了工单定义，用户认为缺少保修期限的影响，
提交“数据不全”及说明。提交时不判断本体是否漏写；内部处理时可能发现规则未表达、
检索未取得、分页未读完、权限限制或 Consumer 理解错误。

## 2. 当前能力与最小增量

| 当前入口 | 可复用能力 | 本期增量 |
| --- | --- | --- |
| [REST semantic.py](../../../backend/app/api/semantic.py)、[MCP semantic.py](../../../backend/app/mcp/tools/semantic.py) | 同一 Context Query 服务、主体身份和获准范围 | 增加独立提交反馈入口及共享反馈服务，不在召回调用中隐式保存 |
| [schemas.py](../../../backend/app/api/schemas.py) 的 SemanticContextQueryRequest／Response | 单／多表达式、过滤与分页参数；公开 scope 含 Ontology 修订号 | 复用查询请求结构；仅在反馈发生时保存客户端提交的必要结果投影 |
| [RecallTestPage](../../../frontend/src/pages/RecallTestPage.tsx)、[workspaceApi](../../../frontend/src/workspaceApi.ts) | 当前 query、实际结果、空结果、降级与加载更多 | 结果旁增加反馈表单，绑定提交时的 query 和实际结果，不使用编辑中的下一条 query |
| [HTTP 权限](../../../backend/app/security/http.py)、[MCP runtime](../../../backend/app/mcp/runtime.py) | read／model／admin、Project 归属、CSRF 与主体绑定 | 提交反馈显式使用 read；内部读取／回填使用 admin，不新增 API Key scope |
| [Delivery](../../../modeling_team/delivery.py)、[Host operations](../../../modeling_team/host_ops.py) | 授权内启动、诊断组织与修复交接 | 内部选取反馈，作为 [029 增量任务](2026-10-12-r4-0-029-incremental-modeling-design.md) 的可选输入 |

当前 Delivery 对话离线会拒绝新消息。本设计独立于该会话，反馈保存在 PostgreSQL，
不依赖 socket、旧 Team 或旧 run。R4.2-008 离线只读聊天合同保持。
不恢复 R4.0-012 停用的 Evidence／lineage 采集，也不自动记录所有召回请求。

## 3. 提交与内部处理接口

以下是待实施合同，不是当前可调用接口。路径均含 API 前缀：

| 接口／工具 | 使用方与权限 | 行为 |
| --- | --- | --- |
| POST /api/semantic/feedback；submit_semantic_feedback | 网页或外部 Agent；read 及所报 Project 访问范围 | 持久保存反馈，返回 feedback_id、received_at 和 received |
| GET /api/semantic/feedback?project_id=…；list_semantic_feedback | 获准内部 Host／Delivery；admin 且 Project 范围匹配 | 按反馈时间及 ID 稳定分页，支持待处理筛选，不触发模型 |
| GET /api/semantic/feedback/{feedback_id}；get_semantic_feedback | 同上；先检查记录的 Project 归属 | 返回原始反馈及处理记录；越权不返回原文或结果快照 |
| POST /api/semantic/feedback/{feedback_id}/resolution；record_semantic_feedback_resolution | 同上 | 追加有来源的诊断及验证结论，不修改原始提交或旧验收报告 |

反馈工具与召回工具并列供消费方接入。list／get／resolution 属于内部工具，不自动放进
外部 Consumer、正式 Examiner／Judge 或生产角色的工具目录。内部 Host 按实际授权选取
资料；普通调用者不能因有反馈 ID 而取得反馈库或模型写权限。

反馈 ID 路由需要在现有 HTTP／MCP 归属解析中映射到反馈表的 project_id；GET 详情与
追加处理记录均先作范围判断再返回／修改。不能只增加 admin scope 而漏掉项目限定。

提交允许 read Key 写入这类操作记录，不能执行模型命令。HTTP required_scope 必须给
POST feedback 单独声明 read；不能沿默认 POST=model 而要求 Consumer 升权。
内部 GET 也需单独声明 admin，不能沿默认 GET=read 泄露别人的反馈。MCP 同步声明
PROJECT_RESOURCE 归属及同等权限。沿用现有用户／Key 的 Project、角色和保护集判断；
不增加新角色、Grant 管理页或反馈权限体系。

## 4. 输入、存储与真实含义

### 4.1 提交输入

| 字段 | 合同 |
| --- | --- |
| feedback_id | 调用方为本次提交生成的 UUID；超时重试保持同一个 ID 和正文 |
| query_request | 复用 SemanticContextQueryRequest 的完整请求，含 Project、scope、query 或 queries、过滤与原分页参数 |
| reasons | 非空、去重的观察标签：incomplete／incorrect／irrelevant／other；可以多选，不是根因分类 |
| description | 1—65536 字符，保留原话；来源说明和期望内容可以写在此处，不要求技术诊断 |
| result_snapshot | 可选的客户端实际收到／展示内容：scope、相关结果、matches_page／context_page、recall、warnings；多页可带 pages 中的各页实际请求及结果投影，空结果同样可提交 |
| snapshot_complete | 是否完整保存所反馈的实际结果窗口；只保留部分相关节点／页时必须为 false，不代表查询本身完整 |

query 的长度、表达式数及参数校验复用现有请求合同。result_snapshot 的 UTF-8 JSON
上限为 256 KiB；超过返回 413 并说明可保留相关结果、标明快照不完整后重试，不静默截断。
没有快照仍可提交；内部如无法可靠定位，保留未知，不以缺快照拒绝收集用户意见。

示意输入（标识仅供说明，不是现有平台资源）：

```json
{
  "feedback_id": "11111111-1111-4111-8111-111111111111",
  "query_request": {
    "project_id": "project-p",
    "scope_mode": "project",
    "query": "返修工单的责任如何判断",
    "search_mode": "hybrid",
    "depth": 0,
    "limit": 20,
    "context_limit": 0,
    "context_detail": "compact"
  },
  "reasons": ["incomplete"],
  "description": "没有看到保修期限对责任判断的影响。",
  "result_snapshot": {
    "scope": {
      "project_id": "project-p",
      "mode": "project",
      "status": "complete",
      "ontologies": [{"ontology_id": "ontology-a", "model_revision": 12}]
    },
    "primary_matches": [],
    "matches_page": {"returned": 0, "truncated": false}
  },
  "snapshot_complete": false
}
```

当前前端 RecallResponse 未声明 scope，需补已有返回字段并保存实际请求／已加载页状态。
单页反馈绑定该实际响应；多页反馈以初次查询作为 query_request，pages 分别携带各页
实际请求、scope 和必要结果，不能拿最后一页的 cursor 冒充整个已加载结果的来源。
前后修订不同的页不拼成一个完整窗口；按页保留并说明差异，或选择单一状态的必要页。
query_request 保留查询范围及过滤，不能只保存文本而丢掉权限／筛选／分页条件。

### 4.2 一张反馈表

建议新增 semantic_feedback 关系表：feedback_id 主键、project_id 外键、服务器生成的
提交主体／时间、原始 submission JSONB、resolution_history JSONB。以
(project_id, created_at, feedback_id) 支持有界查询；不写 RDF，不推进 Ontology.model_revision。

submission 在接收后不可改写。服务器记录真实 AuthPrincipal；客户端不能自称另一个用户，
来源／Agent 名称只能作为客户端声明。相同反馈 ID、同主体、同正文返回原回执；同主体
不同正文返回 409 feedback_identity_conflict；跨主体不透露原记录内容。该检查只解决同次
提交的超时重试，不按相似 query 自动合并不同用户反馈。

result_snapshot、其修订号及所谓期望答案均为客户端报告，不能充当平台实际读取回执或
业务确认。提交接口只检查结构和主体获准 Project／显式 Ontology 归属，不回放召回、
不查询根因，也不为校验历史快照强制当前 workspace 必须 ready。
快照中的输入不能被用来探测受保护资源是否存在；不向提交者回填服务器的受限模型信息。
内部读取仍通过该内部主体当前获准范围，不能借保存快照扩大生产或消费方可见范围。

### 4.3 处理记录

每次处理追加 resolution_id、服务器记录的处理主体／时间、outcome、说明、诊断维度、
实际 run／修复 operation 引用、当次模型修订及验证引用。最小 outcome 为 unresolved、
needs_clarification、resolved、no_change_needed；未处理以没有处理记录表示。
待处理筛选包含无记录及最新 unresolved／needs_clarification，不建立队列领取、工作锁、
自动调度或单独工单资源。

resolved 必须引用同一处理范围及当前相关模型状态上的实际复核，并记录独立结论；仅
应用成功、修复者自测或聊天认可不能闭环模型质量问题。no_change_needed 也要给出可核实
说明，例如已按原过滤／分页条件取得相关内容，或业务澄清证明原定义正确。证据不足只能
unresolved／needs_clarification。接口检验引用身份、结构和范围，不自行判断业务语义。
旧 resolved 只对应其验证时点；本体之后变化，不把该历史结论当作当前模型的验收 PASS。

## 5. 前端及外部 Agent

召回页面在成功返回（包括空结果）后提供“反馈”；打开表单时冻结对应请求及结果投影，
用户只填写原因和说明。切换 query 或 Project 不把旧草稿投给新结果。提交中保留反馈 ID，
明确成功后显示“反馈已保存”，不能显示“模型已修复”或“Team 已处理”。
失败可保留草稿重试；结果未知时以原 ID 重交同正文。首版不增加反馈管理 Tab、建模启动按钮、
自动问答或定时任务。

外部 Agent 先调用召回，再用实际请求／实际结果提交反馈；不能仅依据“没有取得”断言
模型缺失。反馈标签不要求 Agent 完成根因诊断，不把编造的期望内容自动写回模型。
未收到结果时可以只报告 query、现象及限制，明确快照缺失。

## 6. 内部启动、定位和闭环

1. 内部 Host 列出项目待处理反馈，按业务目标选择明确 feedback_ids；不自动读取全部历史。
2. Host 通过 029 内部增量入口发起任务，绑定项目、已有本体、获准资料和本轮授权。
   旧 Team 已停止时，新 Delivery 和新 Team run 读取这些持久输入；不向死线程发消息。
3. Delivery 读取原文，先核对查询范围、分页／降级和反馈时的模型状态。根据当前受治理
   读取组织复现：由 Protocol／获准消费读取者取得实际结果，Delivery 核对公开输入和回执，
   不把 Host 写入对账工具用于业务补查。历史无法复现则明确说明；版本变化不抹去反馈，
   也不把旧问题直接判为当前缺陷。
4. 区分模型表达、召回取得、Consumer 理解、正常可见范围及未知。此为诊断维度；
   运行首失败仍只使用 modeling-quality／platform-contract／collaboration/routing／
   runtime/infrastructure 四层归因。业务不确定只提出来源明确的必要问题。
5. 模型改动由 029 生产角色处理；查询使用或 Consumer 问题修正其使用方式；平台代码问题
   由 023 指定执行者在已有权限内处理，代码修改／部署不从普通增量授权自动取得。
6. 对反馈问题和真实受影响范围取得新读取及独立验证，追加处理记录，保留原提交和旧报告。

用户反馈、早期公开反馈、正式验收失败可共用上述合法诊断／修正路径，但保留来源与判定。
001 不新增“用户手动改 Judge 裁决”操作。隐藏失败不自动生成公开反馈，不把隐藏题／
答案／改写理由装进 029 输入；只有可从获准业务资料独立形成的缺陷依据才能交给生产。
用于修模的公开反馈问题不能再计作隐藏盲测。

首版按需处理，不配置定期拉取、反馈阈值自动启动或后台演进。将来定时触发如有独立授权，
应复用同一个 029 入口，另明确范围、成本及启动额度；本设计不预授该能力。

## 7. 实施交接与验收对应

| 责任面 | 最小改动及验证 |
| --- | --- |
| backend repositories／migration | 新表及反馈 repository；持久化、原文不变、分页和重复 ID 行为 |
| backend services／API schemas／REST | 新 semantic_feedback 服务与独立路由；不要把逻辑塞进 Context Query 检索执行 |
| HTTP／MCP policies、工具注册 | 提交 read、内部 admin、Project 归属及默认拒绝反例；返回不泄露反馈内容 |
| MCP semantic tools | submit／内部 list-get-resolution 同一服务合同，文档同步 REST／MCP |
| frontend types／workspaceApi／RecallTestPage／i18n | query 和结果准确绑定、空结果、部分页、草稿、重复提交及“仅已保存”提示 |
| Delivery／Host 接线 | 选定反馈按允许来源交给 029；不把隐藏验收变为生产资料，处理记录不冒充语义裁决 |

实施时同步 docs/reference/api.md、docs/reference/mcp.md 及接口文档生成入口的实际产物。
按仓库规则执行后端全量 pytest、UI build／Playwright、重启及受影响接口健康；
外部 Agent 的 REST／MCP 同行为和 Team 停止后反馈持久化属于独立功能验收。
实际修正效果另需获准真实运行及独立语义验收，不能用模拟诊断或记录状态替代。
详细验收场景以权威需求 A1—A10 为准。

## 8. 本轮文档检查

需求、决策、设计和相邻前端范围同步；校验本地链接、示例 JSON、Markdown 结构及 diff。
没有执行实现测试或启动服务；未开展独立设计评审／真实建模，后续交付状态保持未实施。
