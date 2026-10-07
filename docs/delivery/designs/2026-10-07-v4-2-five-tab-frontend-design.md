# v4.2 五 Tab 前端重写设计

## 范围与基线

权威范围：[v4.2 需求 R4.2-001—007](../../requirements/requirements-v4.2.md)。
本轮授权：完成设计、审阅及必要修订；不进入开发、服务重启或真实建模。
基线：`dc31fde747a3cb2cda1a8cba2676969af5c2476a`，设计前工作树干净。
状态：需求细化与详细设计完成，独立设计审阅 Round 1 PASS（0 Critical／0 High，
无待确认关键假设）；未开发，功能用例均未执行。

例如用户进入“设备维修”项目，先读项目介绍、当前进度、CQ 与验收摘要；在模型浏览画布
搜索“工单”、切到“流程”视角，再输入“关闭工单需要什么条件”测试相关节点召回。
这条阅读路径只使用五个 Tab，旧运行控制和管理功能不被迁回新页面。

已核对 [v4.0](../../requirements/requirements-v4.0.md) 中 R4.0-002／006／008／012／013
相关合同。普通用户仍以 Key 访问，网页沿用管理员登录；不新增普通用户登录产品。
所有页面业务数据只读，设置中的退出登录为已有会话操作。
用户在设计中再次强调不单独展示 Class：无 Class 专页、专属列表、导航或独立管理界面；
已有资源与分类信息只参与统一图谱和节点阅读，不形成单独的 Class 产品功能。

## 实质决策表

本表是本轮决策主记录；把握是主观设计判断，不是测试概率。

| 编号 | 采用方案与取舍 | 依据／把握 | 来源与状态 |
| --- | --- | --- | --- |
| D1 | 五个同级 Tab；重写 App 页面装配及五个页面，清除旧页面专属代码，Class 不设独立界面 | 用户已明确范围和重写原则，并在设计轮强调不单独展示 Class | 沿用用户确认 |
| D2 | 左侧单层导航、顶部项目选择，保留浅色、白面板、紫色强调；小屏改为横向可滚动导航 | 延续实际样式，消除旧多分组结构；明确超过 85% | 按设计授权采用 |
| D3 | 概览基于当前绑定 run；缺少当前 run 时展示明确标为历史的最近记录，进度保留未知；不合并历史 PASS | workbench 现有当前绑定、公开投影、适用性合同；明确超过 85% | 按设计授权采用 |
| D4 | 图谱按项目各 Ontology 默认 GraphSet 有界加载；视角过滤节点，搜索定位已加载节点，显示部分加载限制 | 现有 resource-list 无续页合同；避免无界全图或假完整；明确超过 85% | 按设计授权采用 |
| D5 | 增加一个通用 resource-relations read-model，连接同一范围内真实 RDF IRI 关系，覆盖非 NamedIndividual 节点 | entity-relations 模板排除 Class 等资源，直接影响画布需求；明确超过 85% | 按设计授权采用，登记必要平台增量 |
| D6 | 召回固定项目范围、hybrid、depth=0，只显示节点主命中与“加载更多” | 用户要求 query 到节点；复用 Context Query 主命中游标；明确超过 85% | 按设计授权采用 |
| D7 | 成员权限只读已有权限角色及 Grant；不请求用户、成员、保护集、Key 列表 | 权威需求已限定展示范围 | 沿用用户确认 |
| D8 | 设置仅语言偏好、当前账号、退出；无健康检查、编辑锁或其他旧设置项 | 用户本轮回答“采用最小清单：语言、账号、退出” | 用户本轮确认，已关闭 |

不采用两种额外路径：旧页面裁剪会保留旧页面状态和专属请求；全新 UI 框架与检索后端会
扩大改动且破坏现有风格。采用新页面配合已有基础能力，平台仅补 D5 的真实缺口。

## 页面布局与视觉合同

```text
桌面：左侧品牌＋五 Tab        顶部：项目选择／当前页面标题
      概览                  内容：当前 Tab
      模型浏览
      召回测试
      成员权限
      设置
```

- 五 Tab 的固定顺序和 URL 值为：概览 `overview`、模型浏览 `model`、召回测试 `recall`、
  成员权限 `access`、设置 `settings`。导航使用链接和 `aria-current`，不嵌套业务子菜单。
- 项目选择是只读下拉框，数据来自 `GET /api/projects`；无项目时显示“暂无可访问项目”。
  不保留项目／Ontology 创建、编辑、删除界面或旧首页管理卡片。没有 Ontology 不阻止进入项目。
- 桌面导航宽度沿用约 254px，正文间距 24—28px，面板间距 18px；图谱页画布占主体，
  节点详情约 320px，只在选中时出现，不挤成旧列表工作台。
- 900px 以下导航改为顶部单行滚动，正文与详情上下排列；390px 时表单换行、文字可换行，
  图谱自身可拖动而页面无横向溢出。图谱至少保留 420px 可操作高度。
- 沿用 [styles.css](../../../frontend/src/styles.css) 中 `--ink`、`--muted`、`--line`、
  `--panel`、`--accent` 等变量：背景 `#f5f6fb`、白面板、主强调 `#6c4df6`，
  Inter／系统字体、现有按钮、圆角、边框和 focus。沿用 Ant Design、Lucide，不新增 UI 体系。
- 实际查看了 v4.1 留存截图 `/tmp/v41-independent-round3-overview-desktop.png` 和
  `/tmp/v41-independent-round3-model-mobile.png`；仅用于颜色、字体和面板基线，旧布局不继承。
  它们属于旧版本 fixture 证据，不作为 v4.2 视觉验收。实施时另存新截图并实际对照。
- 新系统文案接入现有中英文语言机制；项目名、CQ、语义内容与 Grant 原值不自动翻译。
  输入有 label，按钮可键盘操作；图谱复用节点的键盘选择入口，不用颜色作为唯一状态线索。

## 页面、事实来源与交互

接口表中的路径均相对于 `API_BASE_URL`（默认 `/api`）。不新增概览状态库或写入接口。

### 概览

按四块内容排布：项目介绍和一句话进度在上；CQ 与验收进度在下。只有刷新和展示所需的
版本／报告选择控件，不出现运行、审核、冻结、修复、完整诊断或原始 JSON 面板。

| 内容 | 读取与呈现 |
| --- | --- |
| 项目介绍 | 当前 Project 的 name／description；description 为空显示“项目介绍尚未记录”，不从表名或模型节点自动生成 |
| 一句话进度 | workbench 索引与 run 公开 state／host 事件；仅将明确记录的业务阶段／阻塞组织成一句话。只有 RUNNING 等生命周期状态时显示“最近记录已进入运行阶段，业务进度尚未核实”，不推出建模中、进程存活或业务完成 |
| CQ | run 的 artifacts.competency_questions：question_id、question、scope、review_content_version／content_version，以及冻结绑定；不展示参考答案和答案点，原状态缺失显示“状态未记录” |
| 验收进度 | artifacts.reports 中 kind=reports 的正式报告；逐报告显示适用性、范围、分母、原 verdict 计数、未执行、缺口与时点；public_regression_report 不计作正式验收 |

先请求 `GET /projects/{id}/workbench`。枚举完整且 `current_run_id` 非空时读其
`GET /projects/{id}/workbench/runs/{run_id}`，不使用宿主或 Runner 接口。
`current_run_id` 为空且全部已绑定记录都为终态时，读取索引中最近的一条，显式显示
“最近记录（历史）”；进度句为“最近运行已结束；当前项目进度待核实”，不因终态升级为完成。
多个非终态记录、枚举不完整或无记录时不猜当前，进度显示“当前进度尚未核实”，CQ／验收
显示当前数据不可确定。无记录与 HTTP 失败分别表达，不从私有日志生成摘要。

当前 CQ 版本只按公开 host `cq-freeze` 中最后一条有 snapshot_digest 的记录匹配公开投影的
snapshot_digest 和 batch_id；匹配唯一才标“当前冻结版本”。没有匹配或无冻结记录时，已有
投影按 batch_id／digest 分组显示“版本适用性未核实”；历史 run 的投影始终标为历史。
不把不同版本的同名 question_id 合并成当前题集，不把隐藏数量展开成题干。
列表默认前 10 项，超出可“展开其余能力问题”，仍属于概览只读展示。

有多份正式报告时使用卡片内的“验收记录”选择：唯一 `verified_current` 优先；否则按
source.updated_at 选最近的可读正式报告并标历史／适用性未知；多份 verified_current 也不
合并，以时间选择并保留各自范围。报告 mtime 只用于展示顺序，不赋予当前有效性。
如不存在正式报告，显示“尚无正式验收结果”，不以公开回归替代。
公开 verdicts 按 question_id 在本报告内去重计数，与服务端 hidden_summary.verdict_counts
和 unexecuted_count 分组展示。保留原 verdict 名称，不把 model-recall-insufficient 直接改成
“模型缺失”。分母缺失、计数矛盾或未知状态时不计算百分比，显示“进度数据不完整”。
禁止将 `full_pass`、某一局部范围或当前适用性当成全项目语义 PASS；不重新裁决报告。

### 模型浏览

工具栏只有搜索、视角、刷新；主体为图谱画布及可关闭的节点基本详情。
进入项目便读取其获准 Ontology 列表，无全局 Ontology 选择前置。

1. `GET /projects/{id}/ontologies`，逐 Ontology 请求 `GET /ontologies/{id}/workspace-context`。
   仅使用其明确返回的 default_graph_set_id；未就绪时显示该读取范围不可用，不改用其他 GraphSet。
2. 每个默认 GraphSet 读取 `resource-list?include=asserted&field_set=detail&limit=500` 与下节
   resource-relations 投影；按 `source_signature` 核对同一读取范围。签名不同时不拼接图，提示刷新。
3. 资源按完整 IRI 去重成一个节点，保存各 Ontology／GraphSet 位置及其真实字段；不按名称
   或 Class 合并。跨位置字段不同不覆盖，节点详情可选择已有位置读取，不创建新的 Ontology 页。
4. 关系仅来自同一位置已返回的真实 RDF 三元组，按 source／predicate／target 去重绘制并
   保留各位置；两端必须是已加载节点。不能从名称、画布距离或 JSON 文本猜边。
5. 七视角读取 detail_fields.semantic_definition.semantic_role；角色为
   object／behavior／rule／business_role／process／data_mapping／interface_mapping。
   过滤保留具有该显式声明的节点及两端均保留的边；未声明／未知角色只在“全部”显示。
   多位置的明确角色声明可以属于多个视角，详情按位置保留差异，不改变同一 IRI 的身份。
6. 搜索是已加载节点的 label／IRI／已记录业务说明文本匹配。视角决定搜索范围，搜索高亮
   和可键盘选择的匹配菜单帮助定位，保持该视角的图和关系；清除搜索恢复高亮。
   文案为“搜索已加载模型”，匹配数只表示当前视角已加载结果，不自动跑语义召回。
7. 点击节点显示名称、IRI、已声明视角、业务含义、适用范围、当前读取位置和源时点；
   可读原值缺失时显示未知。无需取得完整字段、校验结果或执行脚本后才能看节点。
   必要精确详情使用既有 `GET /semantic/resources/{iri}?graph_set_id=...&include=asserted`。

画布复用 ForceGraphCanvas 的 Cytoscape 渲染、拖动、缩放、布局和键盘节点选择；只增补必要
定位能力，不继承 Classes／Entities 页的增删改、推理状态筛选或图编辑控件。
各范围独立成功／失败，成功范围可看，失败范围明确列为未加载，不宣称项目图完整。
资源 paging.complete=false、关系受限或读取失败都显示部分加载说明；前端不构造续页游标，
不自动加大上限／循环全图加载。没有 Ontology、默认工作空间未就绪、空模型、视角无匹配、
搜索无匹配和部分读取分别呈现。

### 必要平台增量：resource-relations

事实缺口：[entity-relations 模板](../../../backend/app/services/semantic_sparql_templates.py)
要求 source／target 均为 owl:NamedIndividual，且仅 asserted_data 范围，不适合完整节点画布。
不修改该旧投影的兼容行为；在既有 read-model 注册与 service 中增加一个通用只读投影，
通过现有 GET `/semantic/graph-sets/{id}/read-models/resource-relations` 调用，不新增专用 UI 路由。

- 首版固定 asserted_ontology＋asserted_data，`include=asserted`；输出遵循现有
  SemanticReadModelEnvelope，items 每项为 source、target、relation（predicate IRI）、
  label（有则提供）、source_graph_iri、assertion_kind，以及稳定三元组身份。
- 合法端点来自同一 GraphSet 现有 resource-list 的受治理资源身份，包括 Class、属性、
  关系类型、无 Class 实体、Operation、映射和指标。端点窗口沿用 500；关系返回上限 1000。
  查询匹配真实 IRI 三元组，可包含 rdf:type、rdfs:subClassOf 等实际 schema 关系，
  不再要求 NamedIndividual；字面量不是图谱节点，不将注解 JSON 的字符串解析成关系。
- 必须复用 scope resolver、access_view 及已有嵌套引用授权机制。subject、predicate、object
  和展示字段授权先于窗口计数与 LIMIT；不能拿原始 RDF 后在浏览器隐藏受限资源。
  内部固定 fetch 上限命中时返回不完整提示，沿用现有先授权、后截取策略。
- 限定关系端点窗口在真实 RDF 查询之前；稳定排序与去重后再截取获准边，不能先截取整个
  GraphSet 的任意边再与节点相交，否则会把可见节点间关系无声丢失。
- source_signature 与资源列表必须同义；paging.complete 只有端点窗口、关系窗口与底层
  读取均完整才为 true。无边只表示当前窗口无已读关系；无权和不存在继续遵循现有合同。
- 改动仅服务这一通用节点关系缺口，不增加存储表、领域专用谓词、分页框架、Consumer、
  mutation 或模型执行机制。实施前按仓库规则进行 focused impact／GitNexus 可用时的影响检查，
  新投影加真实 RDF 与授权测试，并同步现有接口文档生成器。

### 召回测试

单行／多行 query 输入框、查询按钮、结果节点卡片。按现有 Context Query 请求：

```json
{
  "project_id": "当前获准项目 ID",
  "scope_mode": "project",
  "query": "用户输入",
  "resource_types": ["concept", "instance", "operation", "mapping", "metric"],
  "assertion_types": ["asserted"],
  "search_mode": "hybrid",
  "depth": 0,
  "limit": 20,
  "context_limit": 0,
  "context_detail": "compact"
}
```

该 JSON 为合同示意，不是本轮已发送请求。只读 `POST /semantic/context:query`，显示
primary_matches 的原顺序、label／IRI、Ontology 及已有摘要；不混入 relation／fact 三元组
命中充当节点，不显示 related_context 面板或复杂参数表单。分数默认不展示，不合成置信度。
如果 next_match_cursor 非空，提供“加载更多相关节点”，带原请求及该游标续读并按稳定
result id 去重追加；保留已提交 query 与正在编辑的 query 区别。
仅匹配主命中时，没有上下文展开不当成预算故障；真实 recall 降级、主命中未取完与 warnings
仍以简短说明展示。空输入不提交，trim 后长度 1—2000；只在提交或加载更多时查询。
query 编辑、项目切换立即清空结果和游标；旧请求迟到必须丢弃。游标过期或签名变化保留
明确错误，提供重新查询，不拼接不同模型版本结果。不调用问答、模型写入或外部执行。

### 成员权限与设置

- 成员权限只调用 `GET /projects/{id}/semantic-access-roles`；表格为角色名、描述、Grant。
  使用原 role id 作行身份，每个 Grant 原值作为标签；无 Grant 显示“未配置 Grant”，无角色
  显示“暂无权限角色”。不将业务角色或登录 scope 推导为 Grant，不提供任何管理按钮。
- 设置与是否有 Ontology 无关；语言选择调用 useI18n().setLang，沿用
  `ontology-platform-ui-lang`；账号显示 useAuth().principal.actor；退出使用已有 logout()。
  不展示 Key、配置凭据或 API 地址，不恢复防误操作锁、健康检查与 Ontology 管理。

## 组件、状态与退役清单

前端保持现有 React／Vite，App 仅负责鉴权后项目选择、URL、五页装配；五页的新文件建议为
OverviewPage、ModelBrowserPage、RecallTestPage、MemberPermissionsPage、SettingsPage。
API／类型按消费合同收敛为 workspaceApi／workspaceTypes（少量明确函数和类型）；
不建立页面注册平台或通用业务状态引擎。ForceGraphCanvas、api.ts、AuthGate、main.tsx、
语言 provider、字体与 UI 原语按职责复用；不复用旧页面或其中 FieldTable／ResourceCard。

| 处置 | 文件／分支 |
| --- | --- |
| 重写 | App.tsx 的首页管理、stageMeta／workspaceTabs、Ontology 前置、编辑锁和旧页面装配；新五页及其请求／状态；styles.css 只保留新页面、鉴权及图谱所需规则 |
| 删除旧页 | ProjectWorkbenchPage、ProjectBriefPage、RequirementQuestionsPage、SemanticModelPage、ContextQueryPage、ProjectAccessPage、ClassesPage、EntitiesPage、EntitiesSearchPage、FactAuditPage、GraphSetPage、GraphGovernancePage、BuildContextDebugPage、McpToolsPage |
| 删除旧专属依赖 | workbenchTypes、旧 useWorkspaceLocation 和退役页引用；semanticApi 的写入、推理、校验、导出、治理等前端方法；旧 semantic 组件以及 workbench 组件中不被新页面使用的部分；旧 types／utils／translations 中仅服务退役功能的定义 |
| 保留／按需调整 | api.ts、AuthGate、main.tsx、i18n、基础 UI 与 ForceGraphCanvas；semanticViews 移到新模型页合同位置；实际仍被新页面使用的类型和样式 |

这是按当前源码形成的删除清单；实施时用引用检查确定共享基础文件的保留部分，不能凭目录
名整包删除。删除不涉及 backend、modeling_team、保留 workspaces 或历史 docs。
ForceGraphCanvas 内仅供退役页使用的推理状态展示选项和残留依赖按引用清理，不重写其基础引擎。

URL 只维持 `project`／`tab`；首次进入读取有效项目偏好，URL 优先，无有效偏好时选可访问
项目列表首项。旧、非法 tab 一律 replace 到 overview，旧 ontology／batch／proposal／claim／
item／graph／graphSet／run／version／category 等页面参数从新工作空间 URL 移除。
旧链接仅含 ontology 时回退到已获准项目选择与概览，不通过旧参数恢复旧页面。
新 Tab 偏好使用 `ontology-platform-ui-workspace-tab-v4.2`，不映射旧 Tab 为新业务操作。
清理已知旧页面 UI 偏好（v4 Tab／选中 Ontology／location／编辑锁／旧图布局），保留
项目偏好和语言，不调用 localStorage.clear。新画布默认不持久化布局或节点／响应内容。
返回／前进读取 popstate 并重新规范化 URL；无效／无权 project 只从获准列表选择，不额外
请求探测该项目。设置账号和语言仍可在无项目时使用。

页面依项目身份挂载或明确重置；项目／Tab 切换、刷新、查询变化后使旧请求失效，防止旧
结果覆盖当前页。加载、缺内容、部分读取、403、401 和查询失败分别显示；401 复用现有
auth-required 通道，403 不回填旧数据。无需后台轮询、自动恢复或新的全局缓存。

## 验证、审阅与交接

[验证清单与审阅记录](../test-plans/2026-10-07-v4-2-five-tab-frontend-test-plan.md)
覆盖 R4.2-001—007，包括未授权数据、分页、异步迟到、部分图和历史验收反例。
本轮检查文档链接、编号、需求／决策／设计一致性及源合同；不运行产品测试或重启。
独立 plan_reviewer 只读核对需求、设计、用例和必要源码，报告证据支持的 Critical／High；
有阻塞先修订再复审，不把自查当独立审阅。设计 PASS 不表示开发、功能或真实语义验收通过。

后续实施先完成新五页及通用关系投影、旧代码退役和测试迁移，再执行 frontend build、
全 Playwright、backend 全 pytest、相关接口文档同步；稳定后按仓库规则重启服务和核对
health、前端、resource-relations 与受治理 query。新测试 fixture 只证明功能，不启真实建模。
独立功能验收需另行按开发后实际证据完成，本轮仅交付可实施设计。
