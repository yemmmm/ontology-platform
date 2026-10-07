# v4.2 五 Tab 前端验证清单与设计审阅记录

权威需求：[v4.2](../../requirements/requirements-v4.2.md)。
设计：[五 Tab 前端重写](../designs/2026-10-07-v4-2-five-tab-frontend-design.md)。
本轮仅设计与审阅；以下功能用例全部未执行，不能记为开发或独立功能 PASS。

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
