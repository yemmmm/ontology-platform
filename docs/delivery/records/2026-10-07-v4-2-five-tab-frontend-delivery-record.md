# v4.2 五 Tab 前端交付记录

- 权威需求：[v4.2 R4.2-001—007](../../requirements/requirements-v4.2.md)。
- 设计：[五 Tab 前端重写](../designs/2026-10-07-v4-2-five-tab-frontend-design.md)。
- 共享测试与审阅：[v4.2 验证清单](../test-plans/2026-10-07-v4-2-five-tab-frontend-test-plan.md)。
- 状态：开发、独立功能 Round 1、文档同步与运行重启验证完成。
- 启动日期：2026-10-07（Asia/Singapore）。
- 开发基线：`09af0f3`，开始时工作树干净。
- 交付提交：本记录随 `Rewrite frontend as five-tab workspace` 提交；
  `git log -- docs/delivery/records/2026-10-07-v4-2-five-tab-frontend-delivery-record.md` 可定位不可变 hash。

## 确认范围与继承评审

- 用户已授权本次开发与测试；此前设计独立审阅 Round 1 PASS（0 Critical／0 High），
  无待确认关键假设，复用其结果，不重复设计批准。
- 五 Tab：概览、模型浏览、召回测试、成员权限、设置；重写页面及装配，退役旧页与专属
  前端代码，保持原视觉风格。Class 无独立页面、专属列表、导航或管理界面。
- 设置仅语言、当前账号、退出；权限页只读角色／Grant；新增一个受治理通用关系投影。
- 无新建模、外部业务执行、后端旧功能退役、存储迁移、调度或恢复机制。
- 完成门：相关开发测试、仓库完整前后端验证、接口文档同步、服务重启健康与受影响运行
  接口、独立功能 PASS、状态同步和安全提交；不将本次功能 PASS 提升为语义质量结论。

## 时间线

### 2026-10-07 — 启动与影响核对 — 主 Agent

- 核对适用 AGENTS、需求、已审设计及 16 项验证清单，读取 requirement-delivery 正式交付
  与角色交接合同；设计／测试文档继续复用，不新增竞争计划。
- GitNexus list_repos 显示索引落后 HEAD 216 个提交；impact(App／read_model) 无目标，
  风险 UNKNOWN。不重建索引，使用实际引用检查与 diff，不宣称图覆盖。
- 实际调用点：App 由 main.tsx 装配；SemanticReadModelService.read_model 由 HTTP、
  资源详情及 MCP 共享调用。旧 entity-relations 行为保持，新增投影必须测试旧合同回归。
- 开发分工：前端开发拥有 frontend 下相关源码与测试；后端开发拥有通用 read-model
  服务、模板与新回归测试；主 Agent 拥有文档、接口文档同步、统一验证与重启。
  开发阶段不得自行提交、重启或改写独立审阅／测试记录。

## 独立验收

开发停止写入且测试、重启稳定后交接同一共享测试计划；Round 1 已 PASS，详细结果见下方时间线与共享计划，开发失败轮次永久保留。

### 2026-10-07T20:58:00+08:00 — 开发边界修正 — 主 Agent／后端开发

- focused 首轮 62 passed／1 skipped。后端开发确认只做 postfilter 时，10000 条受限
  predicate 可挤掉后面的可见边，影响 D5 的授权窗口；改为 RDF 查询端排除受限 predicate。
- 可选 label 在共享 access_view.any_unauthorized 检查后，不获准则省略；已经获准的
  subject／predicate／object 关系事实保留，前端以 predicate IRI 作标签 fallback。
  聚合同一三元组／graph 的 label，避免标签重复挤占关系窗口。该细化不改共享授权或旧投影。
- 增加受限 predicate 满窗口和标签嵌套受限 IRI 的回归，独立验收还需验证真实 HTTP 行为。

### 2026-10-07 — 后端开发冻结与全量验证启动 — 主 Agent／后端开发

- 后端 development-ready，停止写入；仅修改 semantic_read_model、semantic_sparql_templates
  及新增 test_semantic_resource_relations（12 个用例），未改旧 entity-relations。
- 最终定向回归：113 passed／1 skipped（21.12s），覆盖实际 RDF 的 Class、无 Class 个体、
  Operation、映射、10000 条隐藏 predicate、后置可见边、受限标签、签名与旧合同回归。
  Ruff 与 owned-path diff 格式检查通过。
- 初始双 VALUES 在大 RDFLib 用例中形成昂贵的组合，运行 138.93s 后中止；端点约束改为
  固定 IN 查询后重新执行并通过。保留该开发失败记录，不将中止计为 PASS。
- 主 Agent 启动完整后端 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q`；
  原始日志在 `/tmp/v42-backend-full.log`。接口生成器 `--write` 显示已同步，手册补充
  resource-relations 的 asserted、窗口、可选标签与真实来源边界。全量结果待记录。

### 2026-10-07 — 前端开发测试首轮修复 — 前端开发

- 新版 build 通过；全 Playwright 首轮 28／30 通过，live-contract 4／4 通过。
  两个失败定位到概览 Questions／Reports 兄弟组件使用相同 React key，刷新后残留旧 CQ。
- 已为两类组件使用不同 key 前缀，重新 build 与全套 Playwright；重生成桌面／小屏截图
  后重新检查。该轮属于开发测试，不是独立验收；失败记录保留，最终结果待记录。
- 主 Agent 阅读发现并交回三个局部修正：summary_by_scope 为对象时未展示，业务阶段
  误按产物顺序取末项，旧 workspace-lock 偏好未清理。开发方已修正并纳入回归。

### 2026-10-07 — 后端全量验证通过 — 主 Agent

- `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q`：
  **1141 passed／54 skipped／18623 warnings，308.25s**，exit 0。
  跳过与警告如实保留，不能据此宣称未运行用例或真实建模通过。
- `uv run python ../scripts/sync-interface-docs.py --check` 通过；相关文档相对链接和
  围栏检查通过。最终 diff、重启及独立功能验收待前端冻结后执行。

### 2026-10-07 — 前端重测与视觉修复 — 前端开发

- React key 修复后重新 build PASS，Playwright **30／30 PASS（8.7s）**。
  旧 57 个仅针对退役 UI 的静态测试声明删除；保留鉴权 2、语言 2、live-contract 4，
  新增 v4.2 实际执行 22 个用例。
- 桌面截图检查仍发现孤立节点标签重叠，故尚未 development-ready；仅调整图谱布局
  的标签尺寸／组件间距后重新检查，不扩大页面功能。上述结果不是最终冻结版本证据。

### 2026-10-07T21:09:19+08:00 — 前端冻结、重启及独立测试交接 — 主 Agent

- 前端 development-ready，停止写入；最终 `npm run build` PASS，
  `npx playwright test` **30 passed（16.9s）**，全工作树 `git diff --check` PASS。
  开发截图 `/tmp/v42-development-{overview,model}-{desktop,mobile}.png` 已逐张查看；
  孤立标签分离，1440px／390px 无文档横溢，画布与上下详情有可用空间。
- 用 HEAD 原测试快照的 Playwright `--list` 校正计数：原 **59 tests／10 files**，
  删除 7 个退役 UI suites 共 51 tests；保留／改写 8 个，新建 22 个，现 30 tests／4 files。
  前一条 57 的静态正则计数误含 regex.test，以本次实际枚举为准。
- systemd 重启成功，active；后端 `/api/health` 为 ok，前端 HTTP 200。运行使用最终
  构建产物；受影响真实 API 与授权反例交独立 tester 验收。
- 独立验收基线为 `09af0f3`＋冻结工作树，产品源／测试文件 SHA256
  `971763f7284d8deda498f4c9766c973a00886d47f2684c937781249532d59f09`；
  tracked diff 留于 `/tmp/v42-independent-baseline.patch`，包含新文件的产品 SHA 单独核对。
- 已向 requirement_tester 交接原共享计划，要求先审实现、追加 Round 1、隔离真实
  PostgreSQL／Oxigraph／HTTP 与浏览器证据及清理，不改产品，不启动或修复真实建模 run。

### 2026-10-07 — 提交前影响工具结果处置 — 主 Agent

- GitNexus `detect_changes(scope=all)` 返回 risk=critical、15 changed、262 affected；
  已向用户明确警示。索引仍落后 HEAD 216 提交，结果包含已删除 RulesPage／FactAuditPage，
  同名 `_TEMPLATES` 出现在几乎全部旧流程，不能作为当前影响覆盖或具体回归证据。
- 核对当前 diff 与调用：新模板仅增加 resource-relations 字典项，既有模板内容不变；
  read_model 仅按新名称分支调用 composer，旧 resource-list／entity-relations 分支未改。
  HTTP 与 MCP 的通用 read-model 调用继续复用同一服务；前端图渲染仅新模型页引用。
- 实际风险为共享读取服务回归与新授权关系窗口，已由 113 定向及 1141 全量测试覆盖，
  独立 tester 继续真实 HTTP／RDF 验收。此处置依据当前代码与测试，不宣称图覆盖；不因
  陈旧全图结果进行无关重构或重新索引。
- 前端完整开发验证整理于 `/tmp/v42-development-verification.md`，当前测试实际枚举
  于 `/tmp/v42-development-test-inventory.txt`，均为本轮验证证据，不包含凭据。

### 2026-10-07 — 独立真实读取阶段结果 — requirement_tester

- 冻结产品 SHA 独立复核一致，实现审查未发现明确缺陷；旧投影与共享授权代码未改。
- 真实 PostgreSQL／Oxigraph／HTTP T08／T09 已通过：Class subClassOf／rdf:type、
  Operation target、无 Class 个体真实边、JSON 不猜边、稳定关系身份与签名、旧
  entity-relations 兼容行为；受限 s／p／o、嵌套 mapping 和隐藏桥不进新 read-model。
- 真实 500 资源／1000 关系有界读取通过，501 个受限前置资源不挤占获准窗口。
  同 IRI 在不同读取位置出现由前端按身份去重，不将多位置解释为重复模型。
- 浏览器与最终清理仍在执行；此阶段结果不提前升级为独立整轮 PASS。

### 2026-10-07 — 独立功能验收与交付收尾 — 主 Agent／requirement_tester

- 唯一共享计划追加 **Independent functional Round 1 PASS**，0 产品缺陷，无需修复复测；
  主 Agent 接受有界功能结论。独立全 Playwright **30 passed（16.8s）**。
- 真实浏览器管理员图 35 节点／9 边，受限 read 32 节点／5 边；实际视角／搜索、跨位置
  身份、hybrid 主命中游标与编辑清空、角色／Grant 及 403 无残留通过。
- 真实公共 CQ／报告投影按 snapshot＋batch 分版本，两版同 question_id 不串数据；
  隐藏 sentinel 不进响应。RUNNING→FAILED 刷新后只保留一个 CQ 区域并标为历史；
  报告原 full_pass、范围与分母保留，不推导全项目语义 PASS。
- independent fixture 的 Key 绑定、Operation canonical 输入、跨位置游标断言等前置
  错误及纠正保留在共享计划；没有将测试数据问题改为产品问题或静默覆盖失败。
- 自有资源清理核查通过：项目／用户／Key 前缀查询均 0，12 个图与产物目录删除，
  私有临时凭据删除。原始日志 `/tmp/v42-independent-{playwright,live,browser,overview,
  boundaries,cleanup}.log` 与截图保留；未修改既有用户模型。
- 冻结产品 SHA256 复核始终一致；复用当前已验证的 build／全后端结果，独立重新执行
  30 项浏览器测试与真实功能验证。同步需求状态、文档索引、UI／平台指南、API 投影说明
  及设计实施补记；不改变已审功能合同。
- 范围偏差仅 D5 的隐藏 predicate 预过滤、可选标签省略及真实来源去重实施细化，已在
  设计中记录。回退 UI 缺陷、源时点排序与图标签重叠均在开发阶段修复并最终重测。
- 有效时间：从开发授权到稳定启动约 20 分钟；独立功能验证及清理约 15 分钟。
  本次不含语义建模，真实 semantic modeling／L1／L2 **NOT RUN**。
- 剩余限制：首版按已确认窗口有界读取／搜索；既有 Vite chunk 大小提示不影响构建。
  GitNexus 索引陈旧的影响核对局限已记录。无待修功能问题或清理阻塞；停止扩展本次范围。

### 2026-10-07 — 提交闭环检查 — 主 Agent

- 最终 8 份变更文档链接／围栏检查通过，接口生成器 `--check` 通过，全工作树
  `git diff --check` 通过；产品 SHA256 与独立验收冻结基线完全一致。
- 核对工作树，只有本轮拥有的后端服务／新测试、前端源码／测试及文档；按明确路径
  暂存并以 `Rewrite frontend as five-tab workspace` 完成提交闭环。提交不包含凭据、
  生成 dist、测试模型或原始数据库内容，不重复无变化的产品测试。


### 2026-10-08 — 结构引用展示补齐与后续检查需求登记

- 用户授权两项工作：补齐模型浏览的结构引用展示；仅登记建模完成后的游离节点检查，
  后者为 [R4.0-024](../../requirements/requirements-v4.0.md#r40-024-建模完成后的模型检查首项游离节点)。
  未启动真实建模、改写现有模型或实施未来检查流程。
- resource-relations v2 同时读取实际 IRI 三元组和既有结构定义中的明确引用；
  definition_ref 按获准窗口内唯一 semantic_id 解析，精确 *_iri／*_iris 指向获准端点。
  兼容当前模型 mapping_payload 的 JSON／安全字典字面量，保留谓词、图位置、字段路径。
  实线与虚线分别展示两类边；不按名称／自由说明猜边，也不向 RDF 补造断言。
- GitNexus context／impact 无当前 composer 符号，使用实际调用点和 diff；detect_changes
  给出 low 但索引陈旧，不宣称图覆盖。变更仅触及指定关系投影、模型画布和相关测试。
- 定向真实 RDF 回归 **16 passed**；前端 build PASS；全 Playwright **31 passed**；
  接口文档生成器 --check PASS；变更文档未引入新坏链接，需求编号／索引唯一，diff 格式通过。
- 开发失败轮保留：授权反例 fixture 的自由说明包含受限 IRI，按已有治理规则正确屏蔽整个
  payload，修正 fixture 后通过；视角反例原选 process，而共享节点在另一读取位置也声明
  process，改为 object 验证真实过滤后通过。均为测试前置错误，未降低产品授权或过滤要求。
- 全后端初轮因 backend 工作目录缺少根目录导入路径，7 个 modeling_team 收集错误；
  按现有运行方式运行 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`，
  最终 **1145 passed／54 skipped（225.42s）**；未将跳过用例报告为通过。
- 新代码在现有 PostgreSQL／Oxigraph 上只读验证：当前 GraphSet
  ec8b5ce0-113f-5c6a-8a03-8d05bf0a54df 返回 **225 边 = 203 真实关系 + 22 结构引用**；
  156 个画布节点，游离节点 **20 → 7**，paging.complete=true、warnings=[]。
  剩余 7 项为无响应体、3 个后续故障／工单定义、SLA target、关闭原因／客户确认引用来源，
  不因展示补齐自动判错、补关系或删除。本证据是只读展示功能回读，不是模型质量验收。
- 本轮独立功能验收及真实语义验收未执行，不继承原五 Tab 独立 PASS 为本轮增量结论。

- 10:12:09+08 服务重启完成，启动就绪后 systemd active、后端 health ok、前端 HTTP 200。
  重启后的真实 HTTP／中文浏览器读取均为 156 节点、225 边，其中 22 条结构引用；
  工单—故障 Join 准确连接工单表与故障表，来源字段两项可定位，page errors=[]。
  首轮浏览器探针未设置中文而断言中文文案，纠正探针语言后通过，产品无变更。
- 实际查看截图 `/tmp/v42-structured-references-live-mapping.png`：Join 两端虚线可见、
  来源字段标签与说明存在，选中节点详情和既有风格正常；完整页面截图及无凭据响应
  保留于 `/tmp/v42-structured-references-live.{png,json}`。以上为开发侧真实功能验证。

## 2026-10-08 节点连接数量与尺寸增量

- 用户要求恢复按边数量调整节点大小；只修改 ForceGraphCanvas 的可见图连接数统计和
  宽高绑定，复用旧版均值／标准差及 tanh 映射，尺寸范围 25～58；实线／虚线均计入，
  视角过滤、刷新后重新计算，搜索不影响尺寸。节点连接数全部相同时统一为 25。
- 新增 `frontend/tests/node-degree-size.spec.ts`，先在原代码复现失败：3 条边与 1 条边的
  节点宽度均为 30；修改后验证连接数与实际 Cytoscape 宽高、同度节点相同尺寸、
  25～58 范围、搜索不变、过滤后重算及刷新后无边的统一尺寸。
- `cd frontend && npm run build` PASS；`cd frontend && npx playwright test`
  **32 passed（8.7s）**，包含新增浏览器回归及既有真实后端合同用例。
- 10:17:41+08 重启 ontology-platform.service，启动就绪后 unit active、后端 health ok、
  前端 HTTP 200；对重启后的构建产物再运行节点尺寸浏览器回归 **1 passed**。
- GitNexus impact 找不到当前组件符号，detect_changes 返回旧 GROUP_PALETTE 符号；
  依据当前源码调用点和 diff 确认唯一消费者为 ModelBrowserPage，不宣称图分析完整覆盖。
- 本轮为开发侧展示功能验证；未执行独立功能验收或真实语义建模验收，不继承原版 PASS。

### 2026-10-08 — CQ 列表与验收进度精简 — 主 Agent 开发验证

- 用户要求全景／切片统一展示、隐藏题题干后追加“(隐藏题)”文字、逐题验收标记、
  CQ 下方单一进度条，并取消历史 CQ 与版本选择；不启动建模，不修改原冻结证据。
- 新增管理员专用 competency-questions 读取：当前冻结绑定优先，无 host 绑定时读取
  唯一最新完整冻结文件；损坏／歧义不回退旧题。题干与可见性进入管理页面，参考答案、
  答案点、私有回答与诊断不返回；原 run 公开投影及生产角色输入保持隐藏题隔离。
- 当前报告必须同批次、同快照且 verified_current；进度统计已获得 pass 或
  model-recall-insufficient 裁决的题数及通过数，公开裁决与隐藏摘要不重复计数。
  待复核／运行未完成／未执行不计作完成，100% 不表示全部通过或全项目语义 PASS。
- 定向回归 16 passed（包含旧 Build Context 复跑与 15 项 workbench 测试）；最终完整
  backend pytest **1150 passed／54 skipped／18960 warnings，228.35s**。
  首轮完整测试 **1 failed／1148 passed／54 skipped**：旧兼容性测试的 generated_at
  分别为 02:31:26 与 02:31:27，其他三个字段相同；独立重跑通过，不改无关测试或产品，
  最终完整复跑通过。原始日志保留在 /tmp/cq-overview-backend-pytest{,-final}.log。
- 最终 frontend build PASS；全 Playwright **33 passed（9.2s）**，覆盖 18 条统一列表、
  旧题隔离、隐藏题文字、逐题裁决、正式报告绑定及唯一进度条。桌面／390px 截图已查看，
  无文档横溢；原始日志 /tmp/cq-overview-playwright-final.log。
- Ruff、接口文档生成／同步检查、相关文档链接与 git diff --check PASS。
  GitNexus 未找到当前 OverviewPage／ModelingWorkbenchService.detail 符号，
  detect_changes 只识别翻译常量、报告 low；实际影响检查采用引用、diff 与测试，不宣称图覆盖。
- systemd 重启后 active，backend health=ok，frontend HTTP 200；真实管理员 CQ HTTP 200
  且 Cache-Control=no-store，返回 **26 条／8 条隐藏题**，不包含答案点，报告
  applicability=verified_current；原公开投影保持隔离。未认证访问返回 401，
  read/model Key 与跨项目访问的 403 由 API 回归验证。
- 结论：本增量开发验证和运行读取验证 PASS；未执行独立功能验收或真实语义建模验收，
  历史独立 Round 1 结果不升级为本次增量的独立验收。

## 2026-10-08 画布视角点击多选增量

- 用户要求以点击选择替换单选下拉，并支持同时展示多个视角；七视角色系图例合并为
  可切换按钮，使用 aria-pressed 表达选择状态。所选视角取并集，未选择或点击“全部”
  恢复全部已加载资源；“清除过滤”同时清除搜索与视角。沿用 IRI 去重与两端可见才画边。
- 新增 viewpoint-filters 浏览器回归，先在原构建复现失败（无视角按钮），实现后验证
  多选／取消、键盘选择、搜索协同、共享节点去重、关系恢复、中文 390px 和空视角恢复；
  更新既有筛选用例并补验多选后节点尺寸重算，保留颜色稳定和结构引用检查。
- `cd frontend && npm run build` PASS；`cd frontend && npx playwright test`
  **41 passed（11.3s）**。构建保留已有大 chunk 提示。本轮没有后端代码变更。
- 14:18:50+08 重启 ontology-platform.service，启动就绪后 unit active、后端 health ok、
  前端 HTTP 200；重启后的多选定向回归 **2 passed（2.0s）**。
- 开发侧真实只读浏览器验证：全部 **156 节点／225 边**，对象 **24／23**，对象＋流程
  **25／23**，点击“全部”恢复 **156／225**，page errors=[]。查看桌面和 390px 截图，
  筛选按钮正常换行，无文档横溢；证据 `/tmp/v42-multiview-filters-{desktop,mobile}.png`
  与 `/tmp/v42-multiview-filters-live.json`。未创建或修改业务模型。
- GitNexus impact 未找到当前 ModelBrowserPage；detect_changes 仅识别翻译常量，risk low。
  当前调用点直接检查确认 App 为页面消费者，筛选只改变传给 ForceGraphCanvas 的节点与边；
  不宣称图分析完整覆盖。相关需求同步与 git diff 格式检查通过。
- 结论仅为本增量开发与运行展示验证；未执行独立功能验收或真实语义建模验收。
