# v5 模型节点数量偏少排查

日期：2026-11-01。状态：只读排查完成；未修改模型或界面。

## 结论

“节点少”和“散点多”有不同原因，不能统一归因为建模失败：

1. **工程验证项目占多数。** 当前保留 38 个 v5 项目、39 个本体，其中 31 个项目是
   有界工程验证、参考用例或反例，不是完整业务模型。许多任务明确只要求 1～3 个概念。
2. **画布存在关系表达的展示盲区。** `owl:ObjectProperty` 定义被隐藏后，其
   `rdfs:domain`／`rdfs:range` 边也被移除；当前读取和画布没有另外展示这组已声明的
   类间关系模式。工业双切片 start3 实有 27 个资源，却投影为 17 个节点、0 条边。
3. **确实保留了未完成业务运行的部分模型。** LLM access start2 只有 5 个 Class；
   工业双切片 start2 也未完成完整关系／指标表达。二者都没有完整范围独立 PASS。
4. **资源数、节点数和业务信息量不相等。** 条件、字段与规则可以存在于资源的语义定义中；
   外部数据库业务行不复制进本体；CQ 是项目能力目标，不是一题一个 RDF 节点。

**不是此前清理导致的数据丢失。** 本次重新导出全部 39 个实际模型图计算内容哈希，
39/39 与清理前保护清单一致，模型修订也一致。当前接口没有出现分页截断或加载失败。

## 核对范围和统计口径

需求依据为 [R5.0-003／004](../requirements/requirements-v5.0.md#r5-0-003) 的完整范围、
应用及实际读回边界，以及 [R4.2-003](../requirements/requirements-v4.2.md)
的图谱投影合同。工程小用例通过不能证明完整业务通过，图连通也不能证明语义完整。

读取当前数据库中的保留项目／本体元数据、实际 RDF 图、绑定任务目标、保留的工作状态与
独立公开评价；对每个本体使用与前端相同的三个只读接口：

- `GET /ontologies/{id}/workspace-context`。
- `GET /semantic/ontologies/{id}/read-models/resource-list?include=asserted&field_set=detail&limit=500`。
- `GET /semantic/ontologies/{id}/read-models/resource-relations?include=asserted&limit=1000`。

然后按当前前端源码重放类型过滤、端点过滤及 IRI 去重，统计“全部视角”下应传入画布的节点／边。
**这些是实际 API 结果加源码投影的确定性核对，不是浏览器渲染测试。** 未读取用户当时选择的
视角或个人权限状态；它们可能进一步缩小用户看到的范围。

| 统计项 | 结果 |
| --- | ---: |
| 保留项目／本体 | 38／39 |
| 工程验证、参考用例或反例项目 | 31 |
| 业务场景运行项目 | 7 |
| 全部视角下不超过 3 个节点的项目 | 29／38 |
| 全部视角下不超过 5 个节点的项目 | 30／38 |
| 按当前投影没有可见边的项目 | 34／38 |
| 实际资源总数／投影节点总数（按本体求和） | 256／167 |
| API 关系记录／投影边总数（按本体求和） | 166／21 |
| 三个接口均成功且 workspace ready | 39／39 |
| 两类读模型窗口均 complete、无截断 | 39／39 |
| 单本体最大资源数 | 40，低于 500 上限 |
| 资源与关系读取的模型修订一致 | 39／39 |
| 实际 RDF 内容哈希与清理前一致 | 39／39 |

166 条 API 关系记录包含 RDF 模式声明和结构引用，不能解释为 166 条业务实例关系。
39 个本体的零边数量为 35；其中双本体工程项目合并为一个项目，所以项目口径是 34。

公开汇总见 [summary.json](../delivery/evidence/2026-11-01-v5-model-size-investigation/summary.json)，
逐项目列出范围分组、资源／投影计数、本体哈希比较与原评价引用。

## 为什么工程模型本来就小

31 个工程项目主要验证运行时、HITL、共享记忆、金额预算、局部应用、父子整合、
多本体落点、checkpoint／fork 和失败恢复。任务范围本来就小，例如：

- `v5-minimal-hitl-20261029-start1`：人工补全一个概念的名称，实际只有一个 Class。
- `v5-memory-snapshot-20261029-start1`：最小单概念任务及共享记忆，不要求扩展业务范围。
- `v5-continuous-20261029-start1`：目标明写 three distinct business concepts，且声明
  是增量能力测试的初始基线，不是完整业务验收。
- `v5-multi-ontology-20261030-start1`：明确只建两个获准 Class，分别落入两个本体，
  禁止增加实例或关系；项目合并后应为两个节点。
- `platform-partial-001`：故意保留第一批写入、第二批未成功的故障验证，不应补齐后冒充成功。
- `v5-composite-contracts-20261030-parent-omission`：父层条件遗漏的独立反例，只有一个 Class。

这些内容来源于对应 `workspaces/v5-runs/*/binding.json` 的 objective，以及
[P0 独立测试记录](../delivery/test-docs/2026-10-28-v5-codex-p0-independent-functional-test.md)
的保留／部分写入状态。v5 表示运行栈和工作方法，不表示每个项目都已完成完整业务建模。

## 为什么有资源但画布仍然像散点

界面的属性／谓词定义隐藏规则符合 R4.2-003 的既定约定；问题发生在它与当前关系读取方式组合时：

1. [workspaceApi.ts](../../frontend/src/workspaceApi.ts) 第 24～25 行读取资源和实际关系。
2. [ModelBrowserPage.tsx](../../frontend/src/pages/ModelBrowserPage.tsx) 第 51～54 行过滤
   `owl:DatatypeProperty` 与 `owl:ObjectProperty`，不将它们画成独立节点。
3. 同文件第 77～83 行要求关系两端都是保留节点，否则丢弃该边。
4. [semantic_read_model.py](../../backend/app/services/semantic_read_model.py) 的
   `_compose_resource_relations` 与 [semantic_sparql_templates.py](../../backend/app/services/semantic_sparql_templates.py)
   的 `resource-relations` 读取实际 IRI 三元组和明确结构引用，没有把 domain／range
   声明另外投影成可见的类间关系模式。

例如实际模型是：

```text
“安装于现场”关系定义 --rdfs:domain--> 安装资产
“安装于现场”关系定义 --rdfs:range ---> 服务现场
```

隐藏“安装于现场”这个 ObjectProperty 节点后，两条边的起点都不可见，因此全部被过滤。
这并不表示模型没有定义该关系。工业 start3 的 10 个关系定义恰好产生 20 条这样的边，
过滤后全部消失。P11 的 2 个 Class＋1 个关系定义也投影成两个孤立节点。

这属于**已声明关系模式的可视化覆盖不足**，不能据此推断实例关系已经存在或应该补写。
`domain`／`range` 是模式约束；不能把它们直接伪装成实际断言的 `安装资产实例—安装于现场—现场实例`。
若修界面，应明确区分“关系模式”和“实际断言／结构引用”，保持只读、授权和真实身份边界。

## 业务模型逐项对照

下表计数为当前模型和“全部视角”投影；评价列是保留的独立报告，非本次新做验收。

| 项目后缀 | 修订 | 实际资源 | 画布节点／边 | 原有独立评价／状态 |
| --- | ---: | ---: | ---: | --- |
| `two-slice-service-20261031-start1` | 3 | 28 | 18／0 | 当前 v2 来源 18/18 PASS |
| `two-slice-service-20261031-start2` | 2 | 40 | 18／10 | 未完成，无完整独立 PASS |
| `two-slice-service-20261031-start3` | 2 | 27 | 17／0 | 原冻结范围 18/18 PASS |
| `llm-access-lab-20261031-start1` | 3 | 19 | 13／4 | 原冻结范围 20/20 PASS |
| `llm-access-lab-20261031-start2` | 1 | 5 | 5／0 | 未完成，无完整独立 PASS |
| `llm-access-lab-20261031-start3`（Demo） | 4 | 14 | 11／4 | v2 模型 30/30 PASS；九题 CQ 能力核对另为 PARTIAL |
| `llm-access-v2-20261101-fresh` | 3 | 13 | 10／3 | 原冻结范围 29/29 PASS |

工业 start2 的实际资源多于已通过的 start3，仍存在关系断言和指标等缺口，说明资源数更大
不能替代业务完整性。保留的工作问题记录也明确区分应用回执与实际关系读回，不以收据中的
`c-rel-*` 条目证明关系已表达。

LLM start2 的五类首批应用成功，随后在 item_id、引用对象包装、business_key 和必填中立字段等
合同上反复失败，仅留下五类。最后工作卡包含“关系类型均已应用”的自报，但当前 RDF 和治理
读回只有五个 Class，不采信自报扩张完成范围。其 Host 控制已 stopped，工作卡的 paused
不表示仍在后台推进。后继 run 的成功不覆盖这次失败，也不能将平台／提示合同问题归因于 GLM
业务语义能力。详情见 [LLM 真实建模记录](2026-10-31-v5-llm-access-modeling-test.md)。

Demo 当前 14 个资源包括 4 个 Class、3 个关系类型、4 个表映射、3 个连接映射；隐藏三个关系
定义后为 11 个节点。条件、字段和业务规则在语义定义／映射载荷中，不按字段逐个建节点。
[九题 CQ 接续记录](2026-11-01-v5-demo-cq-live-validation.md) 的三阶段均为模型 `no_change`，
实际模型保持 revision 4；添加能力目标并不要求增加九个本体节点。CQ 仍有 draft 标准及来源缺口，
不能用既有模型 30/30 PASS 替代九题能力通过。业务行保留在外部数据库亦符合项目语义层边界。

## 处理优先级与证据限制

优先补全“关系模式”的可视化表达，其次在项目列表或说明中区分工程验证、失败保留与已完成
业务范围，避免把所有 v5 项目当作同一类成品。判断模型完整性继续依据来源范围、实际表达、
治理读回和对应冻结版本的独立验收；不为增加节点数而补造概念、实例或关系。

本次没有启动／恢复建模，没有修改 RDF、运行 checkpoint、CQ、预算或业务提示，也没有修改
前后端代码。仅建立临时只读探针并保存调查记录；探针使用的临时管理凭据均已撤销。
未经授权不自动清理保留失败模型或开启修模。

当前源码基线为 `93b2ce456ea473a27c0c3ed8c36f4f1fa6a96816`。GitNexus 未覆盖当前
`ModelBrowserPage` 符号，本次使用精确源码／调用路径与实时 API 核对，没有声称图索引影响分析覆盖。
首次探针误用不存在的 `relation-list` 名称，已纠正为前端实际使用的 `resource-relations`，
本报告只使用纠正后 39/39 HTTP 200 的结果；初次 404 不是平台故障证据。

原始临时证据位于 `workspaces/v5-model-size-investigation-20261101/`：
`model-counts-live.json`、`run-scopes-and-results.json`、`project-counts-and-scopes.json` 与
`hash-comparison-to-cleanup-before.json`。哈希比较基线是
`workspaces/pre-v5-model-cleanup-20261101/cleanup-plan-backed-up.json`，
清理边界见 [此前清理报告](2026-11-01-pre-v5-model-cleanup.md)。

只读探针和报告一致性检查不等于浏览器测试、新一轮独立语义验收、完整 v5 验收或净降耗证明。
