# R4.0-002 多视角语义组织与共享定义：独立功能验收

## 需求、范围与证据边界

- 权威需求：[requirements-v4.0.md](../../requirements/requirements-v4.0.md) R4.0-002 F1—F6、A1—A8；继承 R3.0-009 的统一语义图和 R3.0-004 的不可区分授权合同。
- 本次独立测试覆盖候选合同、Protocol 翻译、确定性写入、治理读取及必要相邻回归，保持共享身份、分类、局部上下文、说明、未知和语义角色可读。
- 不修改产品代码、开发测试或需求，不启动真实 semantic modeling run，不进行外部业务调用、服务重启或提交。
- A8 真实建模和独立语义质量验收未获授权；功能验证不能替代 A8，整体需求语义状态保留 PARTIAL。
- 本文是唯一测试方案与测试轮次记录。每次复测追加记录，不覆盖历史结果。

## 环境与前置条件

1. 在 `/home/yangxiang/ontology-platform` 确认 checkout、适用 AGENTS.md 和当前变更；由主 Agent 通知实现冻结后执行。
2. 使用 backend 的 `uv run` 环境；涉及 Team 模块时使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=..`。
3. 优先复用已有测试、RDFLib 的实际生产 SPARQL 路径及现有 HTTP/PostgreSQL/Oxigraph fixture。必须区分模拟仓储、实际 RDF 引擎与稳定 HTTP 运行证据。
4. 如需要独立组合探针，只写临时或 gitignored 文件，调用真实合同/编译器/读取服务；所有新增资源限定在自有临时 Project 并清理。主 Agent 确认稳定运行就绪后才执行 HTTP 探针。
5. 记录代码基线、变更状态、实际命令、断言及清理结果。代码变化后只复测受影响项和必要回归。

## 测试用例与通过标准

| 编号 | 对应需求 | 步骤与输入 | 期望与通过标准 |
| --- | --- | --- | --- |
| T01 | F1/A1 | 同一对象候选由两个视角/切片引用；通过正式合同验证、翻译、dry-run/apply、资源与关系读回 | 所有引用解析到同一稳定 IRI；回执绑定明确；不产生展示位置副本；引用不改变角色或 Class |
| T02 | F1/A2 | 创建名称相同、含义/范围不同的定义，以及明确同义的多称呼定义 | 同名资源身份保持独立，范围可读；多称呼仍指向获准共享身份，不自动按名称合并 |
| T03 | F2/F3/A3 | 创建无 Class、多 Class、普通分组、正式类型成员、正式子类及跨视角引用 | 无 Class 与多 Class 的既有写读继续成功；普通分组、rdf:type 与 rdfs:subClassOf 可区分；状态/场景不自动变 Class |
| T04 | F3/F4/A4 | 同一共享定义由两个明确上下文使用，一个含局部职责/限制；写读局部说明 | 共享含义保持原值；读回区分两个上下文及局部范围；局部未知不覆盖共享定义；不提前要求 R4.0-004 调用语法 |
| T05 | F2/F4/F5/A5 | 读取对象、分类、属性、方向明确的关系、业务角色与职责；比较缺少说明、显式未知、明确不适用；重复读取治理记录 | 自然语言说明与相应资源/关系关联；名称、含义、范围、单位/多值说明及未知可得；三种状态可区分；角色创建不新增 Grant 或执行权限 |
| T06 | F5/A6 | 同一 principal 精确读取受保护与不存在 IRI；宽查询混合隐藏/可见条目并分页；邻接关系包含受保护端点 | 精确响应状态和形状一致；隐藏资源在排序/计数/分页/cursor 前过滤，关系和元数据无存在性泄露；Project 与 SPARQL scope 既有错误合同保持 |
| T07 | F6/A7 | 读取共同约定的语义声明，覆盖对象/分类/角色路径；让流程/接口语义引用对象 | 读取方依据明确声明识别角色；引用保持对象身份/角色；不以 resource kind、Class、视角名称或旧对话推断角色；其余专属结构留给对应需求 |
| T08 | F1—F6 | 错误候选字段、空/类型错误的语义角色、未解析引用或非法局部上下文；修正后重试同一合同 | 返回准确可操作的合同反馈、不写入不完整内容；合法修正可继续；不引入 Evidence/lineage 补证或新的视角权限硬门；不要求平台代替 Agent 判断业务角色词汇 |
| T09 | A6/相邻回归 | 复用 Batch dry-run/apply、幂等重放、无 Evidence、治理读模型与候选翻译回归 | 无证据主链继续成立，原身份/确定性/授权边界保持；运行未执行项不得记为 PASS |
| T10 | A8 | 后续用户统一授权真实建模及独立语义验收后，按获准资料验证业务含义与职责 | 本次 BLOCKED（未授权），不得据功能测试声称真实语义 PASS |

总体功能 PASS 要求 T01—T09 在适用路径均有证据且无未解决缺陷；缺少实际依赖或运行证据的对应项标记 BLOCKED。开发自测可作为回归证据，但不代替独立输入/断言的验收。A8 未完成时整体语义验收维持 PARTIAL。

## 测试轮次

### 第 1 轮：独立真实依赖探针（2026-10-01，主 Agent 16:44 +08 重启后）

- 代码基线：`0cfe43d2427df187b09327293141e36132bbee56` + 当前未提交 R4.0-002 增量；开发侧已冻结。主 Agent 提供稳定运行证据：systemd active、8001 health ok、5173 HTTP 200。开发必需回归为 backend 1015 PASS/38 SKIP、Modeling Team 2029 PASS/1 SKIP/314 subtests PASS；这些不混称独立验收。
- 独立输入：设备/维修/巡检的自有候选，未复用开发候选；两上下文引用同一 Entity 和 Class，两个同名不同范围节点，零/多 Class、普通分组、正式子类、属性小时单位、审核职责和局部用途，以及缺少说明/显式未知/明确不适用/已知冲突。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python /tmp/r4002_independent_probe.py`；探针无 LLM、无 semantic modeling start、无外部业务调用，使用真实 HTTP/PostgreSQL/Oxigraph。纯翻译和畸形字段验证在实际合同/编译器执行，RDF 三元组核查从 Oxigraph 读出的模型执行。
- 测试资源标识：`accept-4e3c6ba5163a4602896c40967ccd0307`。
- 实际结果：37 项断言通过，覆盖候选回执/确定性翻译/畸形字段拒绝/未知引用反馈/修正重试；四阶段 dry-run、apply_atomic、幂等重放；同名独立身份与范围；零/多 Class、普通分组与子类；局部说明及未知/不适用/冲突；Class/Property/Entity 精确说明读回；两个上下文共用 Entity/Class IRI；审核关系方向。无产品缺陷。
- 未执行项：T06 受保护资源与不存在资源比较、宽读取权限分页及角色授权副作用尚未执行。探针误使用不存在的 `entity-relation-list` 模型名，接口准确返回 `400 {detail: Unknown read model: entity-relation-list}`；这是测试脚本错误。现有接口名为 `entity-relations`，已仅修正临时探针，下一轮继续同一方案。
- 清理：finally 删除自有 Project/API keys/graph registry/state/revision/graph set/audit 记录和 Named Graph；断言 Project/API keys 不存在、全部自有 Named Graph 不存在，`cleanup: true`。
- 结论：本轮功能验收尚未完成，T01—T05/T07—T09 已有主要成功路径证据，T06 未完成；不将测试脚本错误登记为产品 FAIL。A8 未授权、未执行，整体语义状态 PARTIAL。

### 第 2 轮：修正关系读取模型名后复测（2026-10-01）

- 代码/环境与第 1 轮一致，沿用同一方案和命令；测试资源标识 `accept-f1e8fcce3cc541f8a1ed2c31103291dc`。
- 第 1 轮模型名错误 FIXED，既有关系读取成功；先前断言继续 PASS，新增“业务角色未给读取 Key 增加 Grant”“未新增保护集/管理权限映射”PASS，共 39 项已执行断言通过。
- T06 仍未完成：临时 fixture 直接将 39 字符测试标签作为 `SemanticProtectionSetModel.id`，实际 PostgreSQL 为 varchar(36)，flush 返回 `psycopg.errors.StringDataRightTruncation: value too long for type character varying(36)`。这是 fixture ID 错误，产品实现无改动；改为 UUID 形式后继续同一方案第 3 轮。
- 清理 PASS，`cleanup: true`：自有 Project、API keys、Named Graph 均不存在；失败保护集插入已回滚，不保留测试污染。
- 结论：已执行范围 PASS；本轮未判定 T06 最终权限/分页结果，无产品缺陷。A8 未授权/未执行，整体语义状态 PARTIAL。

### 第 3 轮：权限 fixture 修正后的完整功能验收（2026-10-01）

- 代码/环境保持第 1 轮冻结状态，测试方案未变化；同一真实依赖命令退出码 0，测试资源标识 `accept-b607936181914a4882131434fa7b44ee`。
- 第 2 轮 fixture ID 错误 FIXED，未改变产品或开发测试。完整探针 55 项断言 PASS。
- 独立功能结论：**A1—A7 / T01—T09 PASS**，没有发现需要开发修复的产品缺陷。

| 用例 | 第 3 轮状态 | 实际证据 |
| --- | --- | --- |
| T01/A1 | PASS | 正式中性候选回执接受；翻译二次完全相等；四阶段实际 Batch dry-run/apply_atomic/幂等重放；Oxigraph 中两个上下文均指向同一共享 Entity/Class IRI |
| T02/A2 | PASS | 两个“记录”资源 IRI 不同、含义与适用范围不同；补充独立编译探针确认“维修单”“返修记录”两个 skos:altLabel 指向同一共享 IRI，不生成定义副本 |
| T03/A3 | PASS | 无 Class 节点保持空分类；多 Class 节点保留完整双分类；普通分组用业务谓词；正式子类用 rdfs:subClassOf；引用不生成新 Class |
| T04/A4 | PASS | 局部职责说明、明确上下文/source/target/predicate 定义引用同批写入；局部范围/未知/不适用/冲突读回保持，共享定义业务含义未被覆盖 |
| T05/A5 | PASS | Class/Property/Entity 精确读取包含 properties.semantic_definition；属性说明保留小时单位/单值；缺少说明与 unknowns/not_applicable 分别保留；职责方向在 RDF 中明确；角色创建前后 Key 无 Grant、Project 无保护集/管理权限映射副作用 |
| T06/A6 | PASS | 同一个 Class、Property、Entity IRI 在不存在时先取响应，创建并保护后同一读取主体得到完全相同的 404 状态/JSON；entity-list、class-detail、property-list、entity-relations 的可见结果等于独立剔除隐藏引用后的预期集合，limit=1 时仍按可见集合计算 visible_count；响应全文不含隐藏 IRI，受保护端点关系已过滤 |
| T07/A7 | PASS | business_role/object/classification/attribute/relationship/context/local_usage 声明随适用资源读取；补充独立编译探针以 process 角色引用 object 角色资源，原 object 声明和稳定 IRI 保持；不依赖固定平台资源类型或强制 Class |
| T08 | PASS | 空语义角色、数组类型错误、不支持字段均在编译边界拒绝；未知 definition_ref 返回 unbound_definition_reference；使用修正的同一候选可继续翻译；相关重复身份/畸形引用开发回归仍执行通过 |
| T09 | PASS | class/property/entity/relation 四阶段逐项 validated/applied/同 attempt 幂等回放；Project 新增 EvidenceReference 为 0；相关治理、零/多 Class、精确读取分页与候选合同回归通过 |
| T10/A8 | 未授权、未执行 | 不启动真实建模，不调用外部业务系统；不据预设 fixture 判定业务资料忠实度或真实语义质量；整体语义验收保持 PARTIAL |

补充有限相邻回归：

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run pytest -q \
  tests/test_r4002_multiview_semantics.py \
  tests/test_r3009_unified_semantic_graph.py \
  tests/test_semantic_access_authorization.py \
  ../modeling_team/tests/test_r4002_semantic_definition_contract.py --tb=short
```

- 45 PASS（8.29 秒）；无新增 skip/xfail；只有既有 FastAPI/Starlette/RDFLib deprecation warnings。此项复用现有测试证明相邻合同没有回归；独立验收主体为上述独立候选及真实依赖探针。
- 独立别名/角色补充探针：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=..:. uv run python -`；使用独立 `shared-alias`/`process-ref` 候选调用正式 translator/compiler，在 RDFLib 中核对双别名、单共享 IRI、明确流程引用以及共享 object 角色不变，3 项断言 PASS。未创建数据库资源。
- 清理 PASS：第三轮 Project/API keys 全部不存在，Named Graph 从 Oxigraph 删除并逐图确认不存在，`cleanup: true`。前两轮亦已清理；未修改其他已有资源。
- 格式：`git diff --check` PASS；本文需求相对链接检查 PASS。
- 最终结论：**独立功能验收 PASS；A8 真实语义验收未授权/未执行，整体 PARTIAL**。无产品缺陷，无需开发修复或追加功能复测；后续真实建模等待统一授权。
