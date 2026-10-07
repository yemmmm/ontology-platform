# v4.2 五 Tab 前端验证清单与设计审阅记录

权威需求：[v4.2](../../requirements/requirements-v4.2.md)。
设计：[五 Tab 前端重写](../designs/2026-10-07-v4-2-five-tab-frontend-design.md)。
2026-10-07 初始记录仅设计与审阅，功能用例当时全部 NOT RUN；该历史保留于下文。
2026-10-07 已追加 Independent functional Round 1，结论仅适用于冻结实现的有界功能验收。

## 后续功能验证清单

| 用例 | 条目 | 行为与关键反例 |
| --- | --- | --- |
| T01 | 001 | 恰好五个 Tab、固定顺序、默认概览；旧直接链接／非法 tab／旧 localStorage／仅 ontology 参数／返回前进均不能进入退役页；无项目与无 Ontology 可用状态 |
| T02 | 002 | 四块概览真实来源；有唯一当前 run、只有终态历史 run、多个非终态、枚举不完整、无记录、403／读取失败分别展示；进程状态和模型数量不推出业务完成 |
| T03 | 002 | 当前 CQ 通过 snapshot_digest＋batch_id 唯一绑定；两冻结版本复用 question_id 不混合；无冻结／匹配歧义／历史 run 正确标注；原状态未记录不推断已审核；隐藏 sentinel 不进响应、DOM、浏览器存储 |
| T04 | 002 | 单份／多份正式报告、公开回归、verified_current／stale／binding_unknown、局部 PASS、未执行、分母缺失或矛盾；保留原 verdict；去重不重复计数，不拼历史 PASS，不重新裁决 full_pass |
| T05 | 003 | 首屏主体为画布；Class、属性、关系类型、无 Class／多 Class 实体、Operation、映射／指标；同 IRI 跨 Ontology 一个节点保留位置，不因同名合并；有显式 RDF 关系才画边 |
| T06 | 003 | 全部＋七视角过滤、未知角色、跨位置角色差异、搜索和视角叠加、清除、键盘选择与定位、缩放／拖动、节点详情；搜索标明已加载范围，无匹配不声称项目无模型 |
| T07 | 003 | 资源或关系窗口受限、默认 GraphSet 未就绪、一个范围失败、签名不一致；部分加载提示，成功范围仍可读；空图与未加载不同，不自动无限续读 |
| T08 | 003/007 | resource-relations 真实 RDF：Class subClassOf、entity rdf:type、两无 Class 个体关系；不要求 NamedIndividual，不解析 JSON 猜边；端点窗口先限定、获准边去重后 LIMIT；字面量不变节点；稳定身份和 source_signature |
| T09 | 003/004 | 两端／predicate／嵌套引用受限、隐藏桥接、受限节点占据前窗口、仅隐藏资源；计数和 paging 仅基于授权结果，限制提示不得泄露隐藏数；真实 PostgreSQL／Oxigraph／HTTP 功能证据与 fixture 分开 |
| T10 | 004 | 只输入 query 和提交；空白／超过 2000 字符不发请求；固定请求项目 scope、节点类型、asserted、hybrid、depth=0；只展示 primary_matches 节点和原次序，不混入 triples／生成答案 |
| T11 | 004 | 第二页以上主命中追加、游标原请求绑定、query 编辑／项目切换清空、迟到结果丢弃、重复节点去重、游标过期与模型版本变化；真实召回降级、未取完、查询失败和空结果分别展示 |
| T12 | 005 | 已有角色／Grant、无角色／空 Grant、跨项目身份／403；只读取角色列表，无用户／成员／保护集／Key 请求和权限写入；业务角色不当成 Grant |
| T13 | 006 | 语言切换与持久化、账号、退出及重新登录；无项目／无 Ontology 仍可用；英文／中文系统文案完整，原业务内容和 Grant 不改写；无编辑锁、健康检查或其他设置项 |
| T14 | 001/007 | 旧页、装配分支、专属依赖和请求实际删除；Class 无专页、专属列表、导航或独立管理界面；旧的推理／校验／CRUD／导出／运行按钮无可达入口，未搬入详情或设置；后端和历史证据不按前端退役删除 |
| T15 | 007 | 桌面约 1440px 与 390px 截图实际审查；旧视觉基线颜色／字体／面板／控件一致；单层导航、图主体、键盘与 focus、文字换行，页面无横向溢出，图有操作空间 |
| T16 | 全部 | frontend build、全 Playwright；backend 行为变化的更新测试及全 pytest、接口文档生成／差异检查；重启后 systemd active、health、前端及受影响 API；分别记录开发、独立功能和语义未验收 |

## 测试迁移边界

- 新增五 Tab 用例文件（建议 `frontend/tests/v42-workspace.spec.ts`），共享鉴权／语言／
  live-contract 测试按新路由与实际合同调整，保留仍适用的认证、授权及跨项目反例。
- 退役仅测试旧前端功能的 suites：stage2-graph-derived、stage4-tools、semantic-governance、
  build-context-debug、evidence-references、frontend-workflow-reshaping、v41-workbench；
  其中仍与新需求有关的读权限、未知状态、数据绑定等断言迁入新用例，不为留旧测试恢复旧 UI。
- 不删除后端／Team 旧能力测试；新增 resource-relations 用例覆盖实际 RDF 和授权边界。
- fixture 的旧页面 PASS、文档检查、设计审阅和 real-runtime 功能验证分别记录；只有执行过的
  当前环境与版本验证才能升级相应状态，未执行保留 NOT RUN。

## 设计审阅记录

### Round 1 — PASS（2026-10-07）

- 审阅基线：`dc31fde`＋本轮需求细化、设计与本清单的工作树版本。
- 审阅方式：独立 plan_reviewer，只读文档与必要源码，不编辑、不测试、不启动服务。
- 重点：封闭五 Tab 范围、重写与退役、历史／当前数据、通用图谱关系授权和窗口完整性、
  Context Query 合同、已确认设置清单、实施文件和测试迁移。
- 结果：独立 plan_reviewer **PASS**，0 Critical／0 High，无待确认关键假设。
- 审阅证据：确认五 Tab／退役清单／Class 无独立界面与设置范围一致；workbench 的当前
  run、CQ freeze 和报告 applicability 合同存在，设计区分生命周期、业务进度和历史验收。
  entity-relations 的 NamedIndividual 限制有实际模板依据；D5 的授权、端点窗口、
  截取、签名与部分加载条款及真实 RDF／授权用例明确。固定召回请求符合现有 schema，
  主命中游标、异步失效、旧状态清理与测试迁移可实施。
- 独立 reviewer 未编辑、测试、启动服务或提交；本 PASS 仅限设计，不是实现／功能／
  真实语义验收。上表 T01—T16 保持 NOT RUN。

## 本轮文档检查

- 需求—决策—设计—用例一致性、相对文件链接、围栏、R4.2-001—007／D1—D8／T01—T16
  编号与 git diff 格式检查通过。
- 只变更本轮需求、设计、验证清单与文档索引；无运行代码变更，不需要产品测试或服务重启。

## Independent functional Round 1 — PASS（2026-10-07）

### 范围、环境与通过标准

- 独立 tester 先读取 applicable `AGENTS.md`、v4.2 权威需求、设计及本唯一计划，再审实现和执行验证。
  覆盖 R4.2-001—007、T01—T16 的核心成功路径、直接相关失败边界和旧读取投影邻接回归。
  没有修改产品代码、需求、设计或交付记录，没有提交、重启服务或启动真实建模。
- 版本：`09af0f3`＋开发停止写入后的冻结工作树；测试前产品文件 SHA256 为
  `971763f7284d8deda498f4c9766c973a00886d47f2684c937781249532d59f09`。
  哈希范围是 `backend/app/services/{semantic_read_model,semantic_sparql_templates}.py`、
  `backend/tests/test_semantic_resource_relations.py`、`frontend/src`、`frontend/tests` 的
  tracked＋非忽略 untracked 存在文件，按路径排序并拼接 `path\0bytes\0`。
- 实际运行环境：用户 systemd 服务 active；8001 后端、5173 最新 preview、真实 PostgreSQL／Oxigraph。
  独立读取 `systemctl --user is-active ontology-platform.service` 得到 `active`；
  `curl --fail http://127.0.0.1:8001/api/health` 得到 `{"status":"ok"}`，5173 得到 HTTP 200。
- 首轮标准：被测行为与权威合同一致，受限值不进入新关系响应／受限浏览器响应、DOM 或存储；
  当前／历史／部分范围准确呈现；固定查询、游标和迟到请求不串数据；没有未经请求的写入或退役功能。
  失败是 FAIL，外部依赖阻塞是 BLOCKED；测试数据或测试断言错误需记明并纠正，不算产品缺陷。
- 非目标：真实 semantic modeling、L1 Modeling quality、L2 repeatability、外部业务执行与模型业务语义正确性。
  本轮新建的 RDF、公共 CQ／报告文件均是明确隔离的功能 fixture。真实 PG／Oxigraph／HTTP／浏览器
  执行证明运行时功能，不能把人工构造 fixture 叫作真实 Agent 建模质量证据。

### 执行步骤、实际结果与证据

| 用例 | 结果 | 执行与证据边界 |
| --- | --- | --- |
| T01 | PASS | 独立全 Playwright 验证五 Tab、旧 route／非法参数、已知旧偏好清理、返回前进、无项目；新 App 的 URL 与获准项目选取源码检查，无旧页面恢复分支。 |
| T02 | PASS | fixture 测当前唯一／多个非终态／枚举不完整／空记录及终态历史；补测 workbench 403；真实隔离项目无 run 显示未知，随后真实 HTTP 公共投影 RUNNING→FAILED 刷新保持历史／进度未核实。 |
| T03 | PASS | fixture 测匹配歧义、无 freeze、两版同 question_id；真实服务器公共投影按 batch2＋digest2 唯一标当前，切 batch1 标未核实，终态刷新移除当前标签；私有 sentinel／隐藏题 ID 不进入真实响应。 |
| T04 | PASS | fixture 测单／多正式报告、stale、去重、公开回归不替代报告、缺分母；补测冲突 verdict＋分母99显示数据不完整；真实投影显示范围计数、分母3、原 model-recall-insufficient／full_pass=true 和未验证当前适用性，不宣称全项目语义 PASS。 |
| T05 | PASS | 真实管理员画布35节点／9边，受限 read 32节点／5边；真实 Class 参与统一画布，node00 跨两 Ontology 是一个节点且保留两位置和不同业务含义。属性／映射／指标等资源类别及同名不合并由既有 fixture 断言和资源 composer 检查覆盖。 |
| T06 | PASS | fixture 执行全部＋七显式视角、未知角色、视角叠加搜索、不匹配、清除、键盘选择和缩放；真实模型页验证跨位置 process 视角＋搜索、键盘选 Child class、第二位置语义及 Fit graph。 |
| T07 | PASS | fixture 测403范围、默认工作空间缺失、空 Ontology、签名不同和部分范围；真实500资源／1000关系窗口均有界、签名相同、incomplete，关系端点均属于已加载获准资源。 |
| T08 | PASS | 真实 Oxigraph＋HTTP 包含 Child subClassOf Parent、entity rdf:type Child、两无 Class 个体关系、有效 canonical Operation targetResourceType；JSON literal 未产生边；稳定三元组身份／顺序、source_signature；旧 entity-relations 仍无 Class schema 边。 |
| T09 | PASS | 真实 PG ProtectionSet＋read Key 下隐藏 subject／object／predicate、嵌套 mapping 和隐藏桥不进入 resource-list／resource-relations；visible边仍存在。另一独立范围含501个排序靠前受限节点＋510个获准节点，获准资源500与关系1000不被隐藏资源挤占，响应无隐藏IRI；受限真实浏览器网络／DOM／存储无sentinel或凭据。 |
| T10 | PASS | fixture 测空白／超长不请求、原次序、非节点排除；真实管理员与read浏览器都发固定project／hybrid／depth0／context_limit0合同，只显示主节点。 |
| T11 | PASS | fixture 测游标绑定、错误／签名变更、去重、编辑迟到；独立补测跨项目迟到清空 query／节点／游标。真实两页加载后管理员33、read32个唯一IRI；第二位置相同id被前端去重，编辑后立即清空。 |
| T12 | PASS | fixture 测空角色／空Grant／跨项目403及请求清单；真实管理员读取角色和原Grant，read账号沿用403合同显示错误且不残留Grant；没有 users／members／keys／ProtectionSet 请求或权限写入。 |
| T13 | PASS | 独立既有鉴权／语言 suites；真实设置切中文并刷新持久化。无项目设置、账号、退出及再次登录由共享 suites验证；业务文本与Grant保持原值。 |
| T14 | PASS | 独立Playwright物理删除断言＋源码引用检查，退役旧页及专属依赖不存在；只有新五页装配，Class无专页，无旧写入／运行／推理／校验／导出入口；后端旧投影仍在。 |
| T15 | PASS | 独立实际查看 development 和独立 live 的1440／390截图；浅底白面板紫强调、单层导航、四块概览和统一图主体；页面无横向溢出，图高≥420，键盘与focus可用。缩小viewport后通过已有Fit graph重定位，截图分别保留。 |
| T16 | PASS | 独立执行全Playwright 30 passed／16.8s；冻结hash一致，复用当前build、full pytest 1141passed／54skipped／308.25s、focused113passed／1skipped、Ruff及接口文档同步PASS；重启已由主Agent完成，本轮独立复核服务／health／前端和受影响API真实功能。 |

- 实际命令：`cd frontend && npx playwright test`，输出 `/tmp/v42-independent-playwright.log`。
  其中22项v4.2和鉴权／语言4项主要为受控HTTP fixture，4项既有live-contract使用真实后端／Oxigraph。
  本轮重新执行30项均PASS；没有拿退役的旧59项测试结果证明v4.2。
- 真实HTTP／窗口：`cd backend && PYTHONPATH=. uv run python /tmp/v42-independent-live.py`；
  窗口阶段在已登记manifest资源上执行 `PYTHONPATH=. uv run python /tmp/v42-independent-resume.py`。
  日志 `/tmp/v42-independent-live.log`。创建自身随机前缀 Project／Ontology／User／Key／ProtectionSet／Role；
  RDF由独立脚本直接写入唯一归属的Oxigraph图作为读取fixture，不宣称 datasets:load 或Batch写入验收。
  有效Operation使用现有 `operation_quads`／canonical合同构造，无执行。
- 真实浏览器：`node /tmp/v42-independent-browser.cjs`，日志 `/tmp/v42-independent-browser.log`；
  `node /tmp/v42-independent-overview.cjs`，日志 `/tmp/v42-independent-overview.log`。
  API只在内存添加本地测试凭据；公共投影文件位于自身fixture目录，读取前后SHA不变，
  tester仅为当前→历史反例改变自身state fixture，随后删除，不创建或继续建模run。
- 补充既定边界：`node /tmp/v42-independent-boundaries.cjs`，
  `/tmp/v42-independent-boundaries.log` 记录403、无freeze、冲突计数和跨项目迟到PASS。
  脚本复用仓库 `v42-fixtures.ts`，没有另建一套测试方案或语义裁判。
- 视觉：实际查看 `/tmp/v42-development-{overview,model}-{desktop,mobile}.png` 和
  `/tmp/v42-independent-{overview,model}-{desktop,mobile}.png`。前者为fixture、后者为live fixture界面；
  390px图可用Fit graph／缩放阅读，详情位于图下方。
- 实现审查：后端diff只有新模板注册、仅对新名称的asserted限制／分支和新composer；没有修改旧投影
  或共享授权行为。新composer先读取受治理detail端点窗口，查询过滤受限predicate，再去重／排序／截取；
  字面量不成为节点，授权后的可选label含受限引用时省略。GitNexus索引落后且同名符号产生旧流程误触达，
  本轮依据当前diff／调用点／实际回归，不宣称图分析完整覆盖。

### 测试数据纠正、缺陷与清理

- 首轮fixture前置条件纠正：未绑定read Key遭422，mapping直接datasets:load遭既有Batch守卫400，
  非canonical／不完整Operation被既有read-model正确忽略。改为项目绑定Key、直接隔离RDF fixture及
  现有有效Operation codec；失败创建的项目／图／账号均清理。不是产品缺陷或需求降级。
- 首次HTTP游标断言错误地要求不同页不存在相同IRI，真实结果包含同IRI第二Ontology位置；
  本需求明确要求前端稳定id去重，因此改由真实浏览器证明两页唯一节点和不同位置保留。
  原AssertionError保留在live.log，最终真实分页PASS见browser.log。
- 浏览器fixture纠正：跨位置首个label可为第二Ontology值；按IRI搜索定位。初始化脚本不再在每次
  reload强行覆盖语言。read角色403是既有授权合同，按计划验证错误／不泄露，不要求read拥有admin权限。
  报告缺完整摘要digest或模型绑定时保留服务端stale／unknown判定；不替服务端裁决其当前有效性。
  这些纠正没有更改产品实现，最终相关断言PASS。
- 产品缺陷：**0 Critical／0 High／0 Medium／0 Low**；无待修产品问题，无需开发agent修复后再复测。
- 清理命令：`cd backend && PYTHONPATH=. uv run python /tmp/v42-independent-live.py --cleanup`，
  `/tmp/v42-independent-cleanup.log` 记录PASS。最终prefix `v42-independent-8b9749f0ed9f` 的2个项目、
  3个Ontology、各自工作空间图、账号及Keys删除；按准确ID／名称前缀核查归属，图GET404、项目GET404。
  独立查询 `ProjectModel`／`UserModel`／`ApiKeyModel` 的 `v42-independent-%` 均0行；
  公共产物目录删除，私有临时凭据文件删除。早期失败fixture的孤立账号也按确切ID／完整名称删除。
  没有修改或清理现有用户项目／模型；只保留无凭据的脚本、manifest、日志和截图。
- 未执行：真实semantic modeling及L1／L2语义质量验收 **NOT RUN（本轮未授权且不属于功能验收）**。
  本轮不重跑全backend／build，依据相同冻结文件复用其当前已验证结果；这不是未执行当PASS。
  本轮有界功能用例没有外部依赖BLOCKED项；结论 **PASS，仅独立功能验收**。
