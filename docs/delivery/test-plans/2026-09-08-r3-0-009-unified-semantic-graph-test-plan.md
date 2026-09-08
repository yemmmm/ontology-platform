# R3.0-009 统一语义图与共性抽象：共享测试计划

状态：Round 4 两项 High 已修订并通过 Round 5 专项独立复审 PASS（2026-09-08）；历史轮次保留。以下功能测试均**尚未执行**。

关联设计：`docs/delivery/designs/2026-09-08-r3-0-009-unified-semantic-graph-design.md`。
关联需求：`docs/requirements/requirements-v3.0.md` R3.0-009 的 D1-D9、8 项最低验收条件及证据边界。

## 1. 测试目的与边界

本计划验证一个通用的、授权 Graph Set 内的统一语义图合同：零/多 Class、具体分类谓词、IRI 关系导航、
来源与权限保留、009 Team 候选/批准绑定以及普通用户兼容路径。测试必须把平台/流程机械结果和真实业务
语义质量分开记录；机械通过不能替代真实验收。

本轮只形成计划，不启动真实 `semantic modeling start`、不 apply 生产数据、不重启服务。fixture 可使用
临时隔离工作区；业务场景只作通用语义 fixture，不得把 PostgreSQL 业务行复制进 RDF。

## 2. 证据分层、夹具和通用规则

### 2.1 夹具

准备一组最小、可清理的授权 Graph Set：

- `n0`：无正式 Class 的语义节点，含名称、一个合法属性和一条有方向的业务关系；
- `n1`：同时属于两个语义不同的正式 Class，另有一个普通业务分类谓词；
- `c1/c2`：两个都有独立业务证据、最终均获批的共性节点；`c_rejected` 只有重复字段/相同字面量且被拒绝；
- `r1`：`c1` 与 `c2` 间有证据且范围明确的关系，另有 `typical/possible/unknown` 对照项；
- `shape0/shape1/shapeP`：通过新增托管入口创建的无类节点 targetNode Shape、两个 Class 的
  可合并 Shape 和一个显式冲突、使用指定谓词的主语 targetSubjectsOf Shape；不能直接注入 RDF
  来替代平台创建与更新验收。另有未使用该谓词的对照节点，以及无 domain 属性；
- 一个跨 Ontology（同 Project、可授权）和一个受保护资源；受控值包含数据库编码未知的
  `analyzed_not_materialized` 项；fixture 不含客户、设备、工单等业务行。

所有夹具标记 owner、workspace/project、ontology、来源图和清理范围；失败证据保留在隔离目录，不以
后续成功覆盖。

### 2.2 结果规则

每条测试记录输入版本、profile、授权 scope、dry-run/apply、命令/候选 ID、intent/receipt、实际查询
投影和清理证据。区分 `PASS`、`FAIL`、`PARTIAL`、`REVISE` 和 `NOT_EXECUTED`；缺少实际存储/权限/语义
证据时不能写成 PASS。

### 2.3 计划命令

实现阶段按改动面执行（本轮文档没有执行）：

```text
cd backend && uv run pytest
cd frontend && npm run build
cd frontend && npx playwright test
```

同时执行 modeling_team 合同/fixture 校验及 009 profile 的定向测试。后端或前端实现后，按仓库规则测试
通过再重启 `ontology-platform.service`，并检查 backend `/api/health`、frontend `/`；本轮不重启服务。

## 3. 平台与功能测试矩阵

### 3.1 成功路径（S）

| ID | 场景与断言 | 证据 |
| --- | --- | --- |
| S01 | Agent 和用户均可创建、读取、命名、更新、建立关系、删除 `n0`；没有 Class 不生成占位类/空 IRI | 命令、RDF/read model、UI/API |
| S02 | 旧单 Class 输入仍创建成功；新读取返回完整 `class_iris[]`，旧 `class_iri` 仅为兼容投影 | 旧/新 payload 对照与投影 |
| S03 | `n1` 增加/移除一个成员不覆盖另一成员，重复提交幂等且集合顺序不改变 digest | dry-run/apply、receipt、双向读 |
| S04 | 正式成员使用 `rdf:type`；普通分类用具体业务谓词；只有明确批准的集合包含使用 `rdfs:subClassOf` | RDF predicate 与语义查询 |
| S05 | property 无批准 domain、relation type 无 source/target Class 可由普通用户和 009 Team 创建；提供约束时仍校验 | 编译、dry-run、apply/错误 |
| S06 | 关系从节点到分类/共性/规则及反向成员导航均按 IRI 返回 predicate、方向、来源和证据 | context/read model 分页 |
| S07 | 同 Project 且授权的多 Ontology 可跨 IRI 读取；不同 scope 仍隔离 | Graph Set 与 auth evidence |
| S08 | 无类、多类 Shape 均可读；多类约束完整合并，来源 class/predicate 保留 | shape/read projection |
| S09 | 009 候选 stable local ID、证据、unknown、slice/shared scope 映射到确定性平台命令，Protocol 不补业务语义 | candidate、intent/receipt、命令 diff |
| S10 | 基础实体/属性/普通关系/正式 Class/Shape 均绑定候选 revision/digest；节点、每条成员/多重分类、每条共性关系再分别批准；批准命令只含批准版本内容 | stage3 slot、approvals、bindings、receipt |
| S11 | 没有有价值共性时以有依据的拒绝/不物化理由继续；代表性 fixture 仍完成最低样本 | coordinator record、batch result |
| S12 | EntitiesPage 可选 Class/多选分类、显示完整类别并导航；ClassesPage 可反向查看成员；Agent 获得同一能力 | Playwright、API/MCP 对照 |
| S13 | 已注册 r3-0-002 Profile + 新 Task 参数选择009合同；validate/baseline/Runner加载一致，不传formal-only model-profile | CLI与loader定向测试，零semantic start |
| S14 | 新 approvals 同时含旧值确认/stage3 entries、新decisions与translation approvals，均通过各自闭合校验 | schema/读写/角色/交叉引用测试 |
| S15 | 真实存储写入零类 n0 与无 domain 属性后，entity-list、entity-search 词法分支及 property-list 均返回；显式 class 筛选不误包含零类/无 domain | 执行真实模板及 service/API；禁用向量召回仍通过，不用 fake rows 替代 |
| S16 | class_iris 经 HTTP/MCP 的正常 Modeling handler 白名单、payload 校验及 compiler 后完成 dry-run/apply，再在 UI 列表/详情可读 | 外层命令链正例；不能仅直调 compiler |
| S17 | create/update Shape 经正常入口分别接受 target_node_iri、target_subjects_of_iri；RDF target、entity-shape 匹配、guidance 与实际 validation 选择一致 | 真实命令、custom shapes graph、focusNode/sourceShape/resultPath；不直接注入目标 RDF |
| S18 | Shape 更新从 Class 切换至节点/谓词主体目标后旧目标不再生效，删除后不再匹配；跨已授权 Ontology 收集全部匹配 Shape | 更新/删除回执、写后读及实际校验；新增目标进入 009 批准投影 |

### 3.2 边界与分类（B）

| ID | 场景与断言 |
| --- | --- |
| B01 | 空串、空白、占位 IRI 或 `owl:NamedIndividual` 作为业务 Class 被拒绝；正确返回修复字段 |
| B02 | 平台 Examiner 可读到获批谓词限定名称、description、Evidence/lineage 及适用 Rule/Shape；部分/常见/可能不推出普遍继承；同谓词范围冲突被反馈；原 `scope_policy` 使用位置含义不变 |
| B03 | 读取分页、授权过滤、反向关系截断时，`has_more/truncated/complete` 只相对于授权可见集合，不能泄漏隐藏成员存在/数量/分页差异，也不能把当前页当全集 |
| B04 | 受保护节点/类别/关系统一 `forbidden` 或过滤，无名称、数量、分页差异和关系存在旁路 |
| B05 | 同 Project 跨 Ontology 与跨 Project、无授权 Graph Set 对照；仅前者在授权时可见 |
| B06 | 数据库编码未知受控值始终为 `analyzed_not_materialized`，无 Class 路径不能提前物化 |
| B07 | RDF 图中没有 PostgreSQL 客户、设备、工单等业务行；fixture 只包含语义资源/参考值/规则 |
| B08 | 无候选抽象、无 worthwhile commonality 的生产样本不被数量硬门阻断，但缺少代表性验收样本仍失败 |
| B09 | 未物化 candidate/unknown 仅在 Team run 产物/诊断可见，统一 Graph Set/read model 不返回候选当作 RDF 事实 |
| B10 | scalar-only、array-only、同传且匹配/冲突、空数组、重复/乱序成员各有用例；旧标量取首个可见类或 null，不覆盖多类全集 |
| B11 | 合法零类、可见已声明类缺 semantic ID、隐藏类别、实体自身缺 ID 分开验证；合法零类可读，缺类 ID 不抹节点、不伪装无类且相关身份绑定不放行；隐藏类别不产生提示泄漏 |
| B12 | targetSubjectsOf 只选实际使用谓词的主语，非主语及无该谓词节点不匹配；缺必填属性由 targetNode/Class 的 min_count 负例验证，不误用 subjects-of 检查全图 |
| B13 | 类型与实体身份在不同获准图、多类超过分页行数、q/hybrid 同节点命中时仍汇总完整可见类别；无 domain 不自动生成适用于全部类的 Shape |

### 3.3 失败、批准和恢复（F）

| ID | 场景与断言 |
| --- | --- |
| F01 | 候选引用缺失、重复/非法 local ID、未知谓词或缺 evidence 返回对象级 typed feedback，不写入不安全项 |
| F02 | `approved` 缺失、`rejected/deferred`、批准过期、content revision/digest 不匹配均阻断受影响命令 |
| F03 | 共性关系 scope 缺失/不明、节点批准替代成员批准、成员批准替代关系批准均被拒绝 |
| F04 | 修改候选后仅受影响决定过期；未改变的独立决定可复用；不可将旧批准用于新内容 |
| F05 | 修复引用/批准/范围后同一 run 可重试；首次失败证据和第二次结果均保留 |
| F06 | 批次中一个不安全 item 不造成部分 apply；dry-run/apply、workspace version 和幂等边界保持原子 |
| F07 | intent 已保存但响应未知时复用现有 reconcile/kill-switch；不推断“未写入”，不另建恢复机制 |
| F08 | 多 Class Shape 冲突返回 `shape_conflict` 和来源；不取第一类、不静默丢约束、不自动补默认 |
| F09 | `forbidden`、workspace version conflict、旧 receipt/权限锁错误不会泄漏受保护内容，并说明可否重试 |
| F10 | 获批节点创建夹带未获批 `class_iris`、普通属性改写成成员/关系、sidecar绑定正确但实际命令被替换，均在转发前被拒；修正后可重试 |
| F11 | 逐个篡改payload、depends_on、inline/reference证据、rationale、CQ、ontology、candidate版本和bindings，均不能复用原批准；Class集合乱序/重复按明确规则归一化 |
| F12 | 新模式喂旧schema、旧模式喂新schema、参数组合非法、旧intent缺009绑定，不静默降级/迁移；修正合法配置/产物后可继续 |
| F13 | Protocol只能写materialization-plans子目录，不能修改Modeling候选/Coordinator审批；Coordinator可读清单；角色无法读取隐藏题/答案或Runner私有资料 |
| F14 | 在接收前插入版本/摘要不匹配应零转发；在捕获批准快照后修改源路径或发布新版本，转发仍只能使用原获批投影，后续新请求重验新批准；同revision重写拒绝、intent保存失败不转发、较新批次先apply则旧请求workspace-version冲突 |
| F15 | create/update Shape 的目标缺失、多目标、空串、非绝对 IRI、越权引用以及批准后变更 target 均返回可修复错误并零不安全写入；修正后同 run 可继续 |
| F16 | 无类节点的 datatype、min/max_count 违例被实际 SHACL 检出；多来源约束冲突不被 guidance 的后者/custom 覆盖掩盖；隐藏 Shape/target 不经 guidance 或报告泄漏 |

## 4. 兼容与回归矩阵（R）

| ID | 回归范围 | 通过条件 |
| --- | --- | --- |
| R01 | 既有单 Class entity、property、relation type、relation、Shape 创建/读取/删除 | 旧命令和旧读投影不变 |
| R02 | `class_iri` scalar、旧分页 cursor、旧 detail 路由和 MCP `get_ontology_read_model` | 旧客户端无改动可继续工作 |
| R03 | Modeling Batch `extra=forbid`、item 依赖、幂等、lease、dry-run/apply | 009 sidecar 不进入普通 payload |
| R04 | R2.3 class-first task 与 008B stage3/approval schema | 未显式选 009 profile 时行为不变 |
| R05 | 008A `semanticValue`、G7 完整性及 `analyzed_not_materialized` | 无 Class 不成为值物化旁路 |
| R06 | 008B `value_traces`、`l3_nodes`、intent/receipt 和角色写入归属 | 旧 sidecar/receipt 可读、可对账 |
| R07 | RDF Dataset named graph、source/assertion/derived、Evidence/lineage 和 protected read | 不丢图边界、来源或授权信息 |
| R08 | EntitiesPage/ClassesPage readOnly、编辑锁、删除和关系视图 | 用户路径不绕过权限；Agent/API 投影一致 |
| R09 | 规则只按批准 scope 读取/执行；共性描述属性不自动传播 | 无错误继承、默认或类型级关系 |
| R10 | 既有跨切片/跨 Ontology 查询、上下文游标和截断摘要 | cursor digest 和 complete 状态稳定 |
| R11 | 008B v1审批/intent/receipt/ledger原样回放；009新schema保存完整projection并在未知响应后按旧intent对账 | 无旧证据迁移/补造，无重复写；新请求仍核对当前批准 |
| R12 | 原 class-first Protocol 身份绑定、类缺 ID 负例与列表语义召回 identity gate | 旧任务保留要求；009 模式可绑定零类，向量命中仍须当前 canonical 身份，不从索引/IRI 尾段补造 ID |
| R13 | 旧 create/update Shape target_class_id、class-only 读取和未知 payload 拒绝 | 旧类目标合同不变；新增目标只扩明确字段，generated class Shape 不误称通用 Shape |

## 5. 真实语义验收（独立于平台证据）

真实语义测试只能在 009 平台/流程机械增量独立通过、R3.0-006 明确授权且 008B 第二段/011 依赖满足后
执行。语义验收者不得创建、继续、修复被验收 run，也不得修改其保留证据。

| ID | 独立问题 | 必须保留的证据 |
| --- | --- | --- |
| Q01 | 代表场景先有不依赖 Class 的基础图，再有至少一个获批共性节点；同一节点有两个分类维度 | 候选版本、批准、apply 后正反向召回 |
| Q02 | 只有共同字段/相同字面量的候选被拒绝且未物化 | 拒绝理由、RDF/读查询无对应结构 |
| Q03 | 两个获批共性节点间有证据、明确谓词和范围，并能到达适用规则/目标概念 | 关系范围、来源、规则检索上下文 |
| Q04 | 重复样例但不能证明普遍的提升候选被拒绝；无类型级确定性关系/继承 | rejected/deferred 记录与 RDF negative probe |
| Q05 | 缺任一节点/成员/关系批准都不物化对应结构；跨切片共享进入拓扑输入 | 三类批准、命令绑定、拓扑决策 |
| Q06 | hidden/competency questions、授权语义检索和 SQL mapping chain 只使用获准语义 | 独立问答、006 授权、映射/断链证据 |
| Q07 | 真实样本确认 RDF 不含客户、设备、工单行；受控值未知编码仍不物化 | RDF 资源清单、value trace、负向查询 |

真实验收输出单独给出 `semantic PASS/REVISE`；不得以 API/UI/机械测试 PASS 合并替代。

## 6. 清理与完成门

1. 每个 fixture/run 建立唯一隔离目录和 owner；先记录 intent/receipt/失败事件，再清理临时资源。未知写入
   结果必须先完成现有 reconciliation，禁止直接删除以掩盖不确定状态。
2. 清理后复查 Graph Set、Named Graph、candidate/approval/intent/receipt、UI 临时记录和数据库值状态；
   受保护对象及他人 workspace 不在清理范围。
3. 平台/流程完成门要求 S、B、F、R 相关用例和 API/UI/Agent 证据齐全；真实完成门另要求 Q01-Q07、006
   授权、008B/011 依赖、来源/权限/业务行负向证据齐全。
4. 任一层缺证据保持 `PARTIAL`/`REVISE`；不得以未执行测试、编译探针或旧需求证据声明 R3.0-009 完成。

## 7. 计划评审记录（由主 Agent 填写）

| 项目 | 记录 |
| --- | --- |
| 评审状态 | Round 1/2 REVISE、Round 3 PASS 保留；外部 Round 4 两项 High 经核实 accepted-high，修订后 Round 5 专项复审 PASS |
| 发现/处置 | H1/H2/H3 均 accepted-high；审批schema兼容、投影绑定及Task选择路径分别按设计§9.1/9.2/3.2补齐 |
| 测试调整 | 增加S13/S14、F11/F12/F13、R11，覆盖模式分派、完整内容篡改、定向写权限、新旧回放与未知结果对账 |
| Round 2处置 | 批准后固定版本与接收时点已写入设计§9.2；F14验证接收前拒绝、接收后快照不被源路径变更替换及现有工作区版本冲突 |
| Round 3复核 | 独立 plan_reviewer 确认剩余 High 闭合；权威需求、设计§9.2与F14一致，无待确认项。仅计划评审通过，不代表本计划功能/语义测试通过 |
| R4-H1 | accepted-high；新增 S15/S16、B11/B13、R12，覆盖真实列表/词法搜索/属性投影、命令白名单、T0 身份对照及混合召回/Protocol 合同 |
| R4-H2 | accepted-high；新增 S17/S18、B12、F15/F16、R13，fixture 明确经托管入口创建新目标，覆盖匹配/更新/删除/实际违例，不把底层引擎能力当成产品已实现 |
| R4 设计探针 | 2026-09-08，uv run --no-sync python 的内存 RDF/pySHACL 探针：现有列表和搜索均仅返回有类 n1，无 domain 属性列表为空；handler 不接受新增字段；targetNode/targetSubjectsOf 错误 datatype 均 conforms=false，修正后 true。未连接平台存储、未 apply、未启动建模；不是本计划 S/B/F/R/Q 的执行结果 |
| Round 5 专项复核 | 独立 plan_reviewer 确认 R4-H1/H2 直接路径与新增用例闭合，无剩余关键假设；没有扩展审计 context-query 旁路或完整 UI 实现。此 PASS 仅为设计复核 |
| Round 3 文档检查 | 2026-09-08：三份文档的本地链接/路径引用、代码围栏、D1-D9 对应和 56 项用例编号检查通过；34 个现有引用可解析，2 个明确标为待实现的任务/合同资产未创建；git diff --check 通过。只证明当轮文档完整性 |
| R4 文档检查 | 2026-09-08：三份文档的本地链接/路径、代码围栏、D1-D9 与 67 项用例编号检查通过；40 个现有引用可解析，2 个待实现资产仍未创建；git diff --check 通过。功能/语义用例仍未执行 |

平台/流程机械用例已于 2026-09-09 经独立测试 Round 1（FAIL，D1-D12）→ Round 2（FAIL，D2/D13-D15/F08）
→ Round 3（PASS；D16-D18 共 3 项 Low 记录在案，按测试者裁定不阻塞机械验收，随后续批次处理）执行，
记录见 §8-§10；S11/B02/B08/F03/F07/F10 与 Q01-Q07 保持 `NOT_EXECUTED`，待 R3.0-006 授权下的真实
Team run 取证。实现阶段若发现源码合同与本计划冲突，应先记录证据并回修设计，
不能以降低测试范围代替解决需求冲突。

## 8. 独立测试 Round 1（需求测试 agent，2026-09-09）

本轮为独立第三方测试：仅复用本计划矩阵，不改写任何既有轮次/评审记录；未修改任何产品代码；
未提交任何变更；未启动真实 `semantic modeling start`；R2.3 旧任务未被触发为真实 run。

### 8.1 轮次信息与版本

| 项目 | 记录 |
| --- | --- |
| 被测版本 | git `cde5766`（工作区含 25 个未提交实现/测试文件 + 6 个未跟踪文件，其中 `backend/tests/test_r3009_unified_semantic_graph.py`、`modeling_team/tests/test_r30009_unified_graph.py`、`modeling_team/tests/test_r30009_runner_wiring.py`、`modeling_team/references/r3-0-009-unified-graph-contract.json`、`modeling_team/tasks/r3-0-009-unified-graph-real.yaml` 属本需求） |
| 运行时 | systemd user unit `ontology-platform.service`（backend :8001）+ vite preview :5173 + Oxigraph + PostgreSQL，全程未重启，健康检查 200 |
| 夹具 | 独立项目 `0ea43688-07ba-4537-b5a3-606a27e4219b`（名称含 `R3009 Round1 Isolated (r3009r1-1788882242)`、描述标注 owner 与 safe-to-delete）+ main/cross 两个 Ontology + 1 个只读 API key；所有写入均经 `POST /build-sessions/{sid}/modeling-batches` 真实 dry-run/apply，未直接注入 RDF |
| 证据 | 本轮全部原始请求/回执存于临时目录 `/tmp/r3009-round1/evidence/`（00-…/10-…/20-…/30-…/50-…/60-…/70-…/80-…/90-…/95-…/96-…/97-…/98-… 共 100+ 个 JSON；轮次结论文件 `results-stage-c/d/e/f/g/h/i/j/k/l.json`）。该目录属测试临时产物，记录归档后按仓库临时文件规则删除 |
| 复现命令 | `cd backend && uv run python -m pytest tests -q`；`cd frontend && npm run build`；`cd frontend && npx playwright test`；`uv run --project backend python -m pytest modeling_team -q`；`uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r3-0-002-modeling-team.yaml --task modeling_team/tasks/r3-0-009-unified-graph-real.yaml` |

### 8.2 自动化验证（独立复跑，非引用开发方数字）

| 命令 | 结果 |
| --- | --- |
| `cd backend && uv run python -m pytest tests -q` | 981 passed, 36 skipped（注意：从仓库根目录以 `--project backend` 运行会让 9 个用例因相对 fixture 路径误报失败；按本计划口径从 `backend/` 运行全绿） |
| `uv run --project backend python -m pytest modeling_team -q` | 1205 passed, 1 skipped, 318 subtests passed, 7 failed —— 7 个失败全部位于 `test_deepseek_codex_runtime.py` 的 env-file/权限参数化用例；已在 `cde5766` 分离工作树复跑确认与本需求无关（预先存在，环境性） |
| `backend/tests/test_r3009_unified_semantic_graph.py` | 23 passed |
| `modeling_team/tests/test_r30009_unified_graph.py` | 23 passed |
| `modeling_team/tests/test_r30009_runner_wiring.py` | 8 passed |
| `modeling_team/tests/test_r23002.py` | 38 passed, 41 subtests passed |
| `cd frontend && npm run build` | 成功（3.8s，仅 chunk 体积告警） |
| `cd frontend && npx playwright test` | 38 passed |
| `modeling_team validate --profile r3-0-002 --task r3-0-009-unified-graph-real` | exit 0，`model_profile: null`（未传 formal-only model profile） |

### 8.3 逐用例状态（S/B/F/R）

状态口径：PASS=真实存储/真实入口证据齐全；PARTIAL=关键断言通过但部分证据缺失；FAIL=有反证；BLOCKED=被缺陷阻塞无法执行；NOT_EXECUTED=本轮范围外（§5 授权或非目标）。

| ID | 状态 | 证据摘要（真实存储 / 真实入口） |
| --- | --- | --- |
| S01 | PASS | 零类实体 `n0-pump-101` 创建成功（apply receipt `attempt_status=applied`）；entity-list 返回该实体且 `class_iris=[]`、无占位类/空 IRI（`20-entity-list-all.json`） |
| S02 | PASS | 旧 scalar 建实体成功；读取返回完整 `class_iris[]`，`class_iri` 为按 IRI 字典序第一个可见类（n1: `product_type`），仅为兼容投影（`20-entity-list-all.json`） |
| S03 | PASS | 经设计§4.3 路径 `create_relation`/`delete_relation`（谓词 `rdf:type`）加/删成员：加一个成员不覆盖另一成员；重复 add 的 `delta_hash` 完全一致（`b97aa04e…`），删除后集合恢复原状（`97-add/97-del/97-entity-list.json`）。注意每次 apply 仍会推进 workspace revision（乐观锁版本 ≠ 语义内容 digest） |
| S04 | PASS | 正式成员写为 `rdf:type`（export 中 `n1 a owl:NamedIndividual, <product_type>, <safety_category>`）；`rdfs:subClassOf` 未被普通分类路径生成（`54-export-shapes.trig`） |
| S05 | PASS | 无 domain property（`nominal_power`）与无 source/target 的 relation type（`usually_requires_inspection`）均由同一用户级 Modeling batch 创建成功；提供 domain/source/target 时仍校验（`10-properties-apply_atomic.json`、`10-relation-types-apply_atomic.json`） |
| S06 | PASS | `entity-relations` 返回 predicate/direction/source/target/source_graph_iri（`40-entity-relations-n0.json`） |
| S07 | PASS | 建 project-scope Graph Set 同时纳入 main+cross 两个 Ontology 的 named graph 后，entity-list 同时返回 main 的 `n0-pump-101` 与 cross 的 `x-compressor-9`（`62-two-ontology-graphset.json`/`62-two-ontology-entities.json`） |
| S08 | FAIL | 多类实体 n1 只收集到**生成 Shape**（blank node id），两类各自的自定义 Shape（`shape1-class-target`、`s08-safety`）全部缺失；`class_iris` 全集正确（`61-entitieshape-s08-multiclass.json`）。根因见 D1 |
| S09 | PARTIAL | 合同/映射由 `modeling_team/tests/test_r30009_unified_graph.py` 23 用例与 `test_r30009_runner_wiring.py` 8 用例覆盖（candidate→命令、Protocol 不补语义）；本轮未做 Team 真实 run（R3.0-006 授权未开放） |
| S10 | PARTIAL | stage3 slot/approvals/binding 闭合由同一组自动化用例覆盖（`test_candidate_revision_and_approval_closures`、`test_binding_receipt_rejects_digest_and_state_drift`）；无真实 run 证据 |
| S11 | NOT_EXECUTED | 需真实 Team run（价值判断/代表性样本），R3.0-006 授权未开放 |
| S12 | PARTIAL | EntitiesPage/ClassesPage 展示 `class_iris`（`frontend/src/pages/EntitiesPage.tsx:38,49-50`、`ClassesPage.tsx:67,774-775`）；Playwright 38 用例全绿；Agent/MCP 同一能力的对照与“多选分类写回”未验证（写回路径见 D12） |
| S13 | PASS | `validate` 通过且 `model_profile: null`；`test_s13_unified_task_selects_the_009_contract`/`test_s13_008b_task_keeps_the_unified_flow_disabled` 通过 |
| S14 | PASS | 新旧 approvals/intent/receipt 闭合校验用例全绿（`test_candidate_revision_and_approval_closures`、`test_legacy_intent_and_receipt_stay_on_the_old_contract`、`test_unified_intent_and_receipt_round_trip`） |
| S15 | PASS | 真实存储写入零类 n0 与无 domain 属性后，entity-list/entity-search(lexical)/property-list 均返回；显式 class 过滤不误含零类、不误含无 domain 属性（`20-*.json`） |
| S16 | PASS | `class_iris` 经 HTTP Modeling handler 白名单→compiler→dry-run/apply 全链路成功，并在 read model 可读（`10-entities-*.json`） |
| S17 | FAIL | `target_node_iri`/`target_subjects_of_iri` 可经正常入口 **dry-run/apply**（`target_subjects_of_iri` + min_count=1 applied；`30-shapep-apply.json`）；但 entity-shape guidance 始终为空、与实际校验选择不一致（`61-*.json`）。根因 D1；另见 D2（min_count≥1 的节点目标 Shape 一律被拒） |
| S18 | PARTIAL | 目标切换/删除的**实际校验效果**已验证：节点目标在 switch/delete 后旧目标不再约束（`95-n5-blocked`→`95-n5-after-switch` applied；`95-n3-blocked`→`95-n3-after-delete` applied）；跨已授权 Ontology 的自定义 Shape 收集失败（`61-entitieshape-xcross-entity.json`，根因 D1）；“新增目标进入 009 批准投影”未验证（无 Team run） |
| B01 | PASS | 空串/`owl:NamedIndividual`/相对 IRI 作为业务 Class 均被拒且返回可修复 finding（`30-b01-*.json`）；relation 命令伪造 NamedIndividual 被拒（`97-forge.json`） |
| B02 | NOT_EXECUTED | 需 Examiner 视角与真实 run 产物；本轮无 009 run |
| B03 | FAIL | entity-list/entity-relations/property-list 在 `limit=1` 时只返回 1 行，但信封无 `total/has_more/truncated/complete/next_cursor` 任何分页元数据，当前页与全集不可区分（`98-pagination.json`） |
| B04 | PARTIAL | 受保护成员由 access_view 过滤的路径存在（`semantic_read_model.py` 的 `is_member_visible` 分支）；本轮未构造受保护对象（避免触碰他人 workspace），未取得泄漏负向证据 |
| B05 | PASS | 跨项目用 project 级 key 读他人 Graph Set → 404 且无 items；把他人 graph IRI 挂到自己 Graph Set → 无数据返回（`53-isolation-*.json`） |
| B06 | PARTIAL | “未知受控值不提前物化”由既有 008A/008B 用例与 R05/R06 回归覆盖；本轮未构造业务受控值 fixture |
| B07 | PASS（fixture 级） | export 显示 RDF 仅含语义资源（class/property/relation-type/entity/shape），无客户、设备、工单业务行（`54-export-shapes.trig`） |
| B08 | NOT_EXECUTED | 需真实样本与 Team run 数量硬门验证 |
| B09 | PARTIAL | read model 未返回 candidate/unknown 为 RDF 事实（entity-list 中无候选对象，`20-entity-list-all.json`）；Team 产物侧由自动化用例覆盖 |
| B10 | PARTIAL | create 时 scalar/array 同传冲突→`class_membership_conflict` 存在但以 **HTTP 500** 冒出（见 D5）；重复/乱序/空数组均归一化且 dry-run 通过（`30-b10-*.json`）；update_entity 不接受 `class_iris`（与设计一致：成员变更走 relation 命令，见 §4.3） |
| B11 | PARTIAL | 合法零类可读（S01）；“已声明类缺 semantic ID / 实体自身缺 ID / 隐藏类别不泄漏”未构造（无法经托管入口制造缺 ID 资源），仅 code-level 证据 |
| B12 | PASS | `targetSubjectsOf` 只选实际使用谓词的主语：无该谓词的 n6 创建不受影响（`95-n6-create` applied）、谓词使用者违例被检出（`95-n5-violate`）、删除 Shape 后同一写入放行（`95-n5-allowed`）；缺必填属性由 targetNode/Class 的 min_count 负例检出（`95-mincount-neg`） |
| B13 | PARTIAL | 多类汇总、无 domain 不自动生成全类 Shape 已由自动化用例覆盖（`test_entity_list_aggregates_zero_multi_and_bare_class_entities`、`test_property_list_anchors_on_declared_domain_only`）；“多类超过分页行数”因 B03 分页元数据缺失无法验证（见 D9） |
| F01 | PARTIAL | 对象级 typed feedback 由 Team 合同用例覆盖；本轮未构造缺 evidence 候选 |
| F02 | PARTIAL | `test_candidate_revision_and_approval_closures`、`test_unified_submission_rejects_a_stale_candidate_revision` 覆盖；无真实 run |
| F03 | NOT_EXECUTED | 需真实 run 的三类批准混淆场景 |
| F04 | PARTIAL | `test_candidate_revision_and_approval_closures` 覆盖版本/digest 失配 |
| F05 | PARTIAL | F06 的修复后重试已实测（`98-atomic-good-only` applied）；“同一 run 重试且首次失败证据保留”需 Team run |
| F06 | PASS | 混合批次（1 合法 + 1 非法字段）整批拒绝，实体数量与 workspace version 均不变，修正后单独重提成功（`98-atomic-mixed`/`98-atomic-good-only`） |
| F07 | NOT_EXECUTED | 需真实 intent/未知响应场景（不得人为制造不确定写入） |
| F08 | BLOCKED | 多 Class/多来源 Shape 冲突的 `shape_conflict` 无法经真实入口触发：自定义 Shape 永不进入 guidance（D1），故两个并存冲突 Shape 的 `entity-shape` 读取恒为 200+空（`61-entitieshape-f08-conflict.json`）；合并/冲突逻辑本身在单元级可触发（`test_entity_shape_conflict_surfaces_as_409_shape_conflict` 通过），说明是产品接线缺陷而非引擎缺陷 |
| F09 | PARTIAL | 越权读 404/无泄漏（`53-isolation-read.json`）；workspace version conflict 的行为已实测（乐观锁 409 + `current_workspace_version` 回执），未发现受保护内容泄漏 |
| F10 | NOT_EXECUTED | 需 Team 转发链路真实 run |
| F11 | PARTIAL | `test_payload_drift_is_rejected_even_with_a_correct_self_reported_digest`、`test_digest_rules_are_canonical_and_order_insensitive_for_class_iris` 覆盖；`class_iris` 乱序/重复归一化已实测（`30-b10-dups`） |
| F12 | PARTIAL | `test_b_unified_artifact_schema_drift_is_typed`、`test_partial_009_intent_arguments_are_rejected`、`test_legacy_intent_is_never_retrofitted_with_009_bindings` 覆盖 |
| F13 | PARTIAL | 角色写权限由 `test_plan_ref_must_live_in_the_published_directory` 等覆盖；未做真实 run 的目录级写探针 |
| F14 | PARTIAL | `test_unified_submission_closes_receipt_against_the_saved_intent`、`test_intent_and_receipt_bindings_are_kill_switch_triggers` 覆盖；接收时点快照的真实转发未验证 |
| F15 | PARTIAL | 相对 IRI 拒绝（`30-shape-relative-iri`）；**多目标、空串、零目标**被拒但以 HTTP 500 冒出且无 typed finding（D5/D6）；“越权引用”与“批准后变更 target”需 Team run/批准流 |
| F16 | PARTIAL | 无类节点的 datatype/min_count 违例可被实际 SHACL 检出（`80-f16-neg` 拒绝写入；`95-n3-blocked`）；但违例 finding 只带 `conforms:false`，无 focus node/path（D8）；“冲突不被 guidance 掩盖”因 D1 无法验证 |
| R01 | PASS | 旧 scalar Class 实体、property、relation type、relation、class 目标 Shape 的创建/读取全部成功 |
| R02 | PASS | 旧 `class_iri` 兼容投影、detail 路由正常；`get_ontology_read_model` 的 MCP 对照未单独执行 |
| R03 | PASS | `extra=forbid`、FORBIDDEN_TARGET_FIELDS（携带 `ontology_id` 被 `forbidden_target_override` 拒绝）、幂等、lease、dry-run/apply 均实测；009 字段不进入普通 payload |
| R04 | PASS | R2.3/008B 回归：`test_r23002.py` 38+41 subtests passed；008B suite 全绿 |
| R05 | PASS | 008A 相关回归全绿（981 passed 内含） |
| R06 | PASS | 008B `value_traces`/`l3_nodes`/intent/receipt 回归全绿 |
| R07 | PASS | named graph 边界保留：export 显示 ontology/data/shapes/policy 各图分离，evidence/lineage 字段在回执中保留 |
| R08 | PASS | Playwright 38 用例（含 readOnly、编辑锁、删除、关系视图）全绿 |
| R09 | PASS | 规则按批准 scope 的回归用例全绿 |
| R10 | PASS | 跨切片/Ontology 查询与游标回归用例全绿 |
| R11 | PASS | 008B v1 回放与 009 新 schema 保存用例全绿 |
| R12 | PASS | `test_zero_class_ref_*`、`test_incomplete_class_identity_is_reported_and_never_proves_a_class`、`test_entity_list_hybrid_recall_keeps_canonical_rows` 全绿 |
| R13 | PASS | 旧 `target_class_id` Shape 创建/读取正常（`30-shape1-apply` applied）；未知 payload 拒绝（`test_registry_accepts_009_fields_and_keeps_rejecting_unknowns`） |
| Q01-Q07 | NOT_EXECUTED | 按 §5 与本轮边界：R3.0-006 授权未开放给 009，且需 008B 第二段/011 依赖；不得以机械测试合并替代 |

统计：PASS 26；PARTIAL 22；FAIL 3（S08、S17、B03）；BLOCKED 1（F08）；NOT_EXECUTED 8（S11、B02、B08、F03、F07、F10、Q01-Q07）。
（S/B/F/R/Q 状态以本表为准；上轮评审记录与本表互不影响。）

### 8.4 缺陷清单（按严重度）

| # | 严重度 | 缺陷 | 复现（真实入口） | 期望 / 实际 | 设计条款 |
| --- | --- | --- | --- | --- | --- |
| D1 | High | 自定义 Shape 与 guidance 读取的 named graph 不一致：`ModelingCommandHandler.prepare` 把 Shape 命令目标图改写为 `…/graph/shapes/{ontology}`（`backend/app/services/modeling_handlers.py:504-526`），而 `SemanticShapeEndpointService` 只读 `…/graph/shapes/{ontology}/custom`（`semantic_shape_endpoint_service.py:79-83`、`92-96`、`170-172`）。该子图从未被写入，`get_graph` 抛 `RdfStoreUnavailable: … does not exists` 后被 `except Exception: Graph()` 吞掉 | ① `create_shape`（任一 target）apply 成功；② `GET /graph-sets/{gs}/read-models/entity-shape?entity=…`；③ `GET /graph-sets/{gs}/shapes/classes/{class_iri}` | 期望：apply 过的 Shape 出现在 entity-shape/class guidance 并参与冲突合并（§6.1、§9.2）。实际：`fields/targets/shape_iris` 恒为空（class 读取同样为空），只有生成 Shape 出现；store 内实际存有 4 个 NodeShape（`shapes` 图 29→65 triples），并实际驱动 SHACL 校验 | §6.1、§9.1（shapes 角色与读投影）、F08、S08/S17/S18 |
| D2 | High | Shape 命令的 SHACL 校验把 **shapes 图当作 data 图**校验：`_validate_candidate` 以 `delta.affected_graph_iris()` 为候选数据（`semantic_canonical_write.py:347-372`），Shape 命令的受影响图已被改写为 shapes 图 | `create_shape` + `target_node_iri=<已存在实体>` + 任一 `min_count>=1` → HTTP 200 `attempt_status=validation_failed`（`shacl_violation`）；改为 `min_count=0` 即 applied | 期望：以 Ontology 数据图为候选校验，存在目标实体且满足约束时可通过（§6.1 的新目标应可用）。实际：shapes 图内不存在该 focus node → minCount 恒违反，新目标最常用路径被阻断 | §6.1、S17、F15、F16 |
| D3 | High | Shape 约束 `path_id` 传入绝对 IRI 时被二次封装：`ns.resource('property', path_id)` 总是加前缀并百分号编码（`semantic_command_compiler.py:1055-1060`、`semantic_export.py:24-27`），生成 `…/property/http%3A%2F%2F…` 的假谓词 | ① `create_property serial_no`；② `create_shape` + `target_subjects_of_iri=<serial_no 绝对 IRI>`、`path_id=<serial_no 绝对 IRI>`、`min_count=1`（apply 成功）；③ 任何使用 `serial_no` 的实体写入 → `shacl_violation`，pySHACL 报告 Source Shape 的 `sh:path` 为该假 IRI | 期望：绝对 IRI 原样作为 `sh:path`（或明确拒绝并提示用 local id），约束落在真实谓词上（F16、B12）。实际：约束落在不存在的谓词上，既检不出真实违例，又会否决合法写入 | §4.1、§6.1、F16 |
| D4 | High | 009 批准合同缺少 `member_relation` 决定目标类型：`DECISION_TARGET_KINDS = ("commonality_node","commonality_relation")`（`modeling_team/staged_decisions.py:102`），合同 JSON 同为两项（`modeling_team/references/r3-0-009-unified-graph-contract.json:76`）；`validate_unified_approvals` 返回 `approval_missing / decision d-member-1 target_kind is invalid` | 提交含 `target_kind=member_relation` 的 decisions（探针 `member_relation_repro.py`，输出 `member_relation_result.json`） | 期望：成员级关系可独立批准（§5.2，最低验收条件 5 的“节点、每条成员/多重分类、每条共性关系分别批准”）。实际：该 target_kind 无法记录，成员/关系级批准无法落库 | §5.2、需求最低验收条件 5、S10、F03 |
| D5 | High | `ClassMembershipConflict` / `ShapeTargetConflict` 继承 `CommandCompilerError` 而非 `InvalidCommandPayload`，批次入口只捕获后者，导致 **HTTP 500 "Internal Server Error"**：① `create_shape` 目标字段为空串或全部缺省；② `create_entity` 的 `class_iri_or_legacy_id` 不在 `class_iris` 中（`modeling_batches.py:767-790` 的 `_compile` 映射 + `except InvalidCommandPayload`；异常定义见 `semantic_command_compiler.py`；服务端 traceback 见 journalctl `raise ShapeTargetConflict / ClassMembershipConflict`） | 上述三个 payload 经 `POST /build-sessions/{sid}/modeling-batches` 提交（dry-run 同样触发） | 期望：按 §8 返回可定位 typed finding（4xx + `code=path`），与 handler 已有的 `shape_target_conflict` 一致。实际：500 且响应体无任何 finding/code/path（`30-shape-blank-target-dry_run.json`、`30-shape-no-target-dry_run.json`、`30-b10-conflict-dry_run.json`） | §8、F15、B10、B01 |
| D6 | Medium | 多目标 Shape 的拒绝 finding `code` 为通用 `invalid_command_payload`，typed 代码只出现在 message 文本 `"shape_target_conflict: combine target_class_id, target_node_iri into separate shapes…"`，`path=["items",0,"payload"]` | `create_shape` 同时给 `target_class_id` + `target_node_iri`（dry-run） | 期望：finding `code=shape_target_conflict` 且逐字段可定位（§8、§6.1）。实际：code 不可机读，只能靠字符串匹配 | §8、F15 |
| D7 | Medium | 读模型分页无任何“窗口”元数据：`limit=1` 只回 1 行，信封无 `total/has_more/truncated/complete/next_cursor`（entity-list、entity-relations、property-list 均如此；路由仅有 `limit` 参数） | `GET /graph-sets/{gs}/read-models/entity-list?field_set=detail&limit=1` | 期望：B03 要求 `has_more/truncated/complete` 相对授权可见集合明确表达，当前页不得被当作全集。实际：调用方无法区分窗口与全集 | B03、§4.1 分页 |
| D8 | Medium | `shacl_violation` finding 不含任何定位信息：`details.report_summary` 只有 `{"conforms": false}`，message 为固定句，无 focus node / path / source shape（`modeling_batches.py:1001-1023`）。真实报告文本在服务内部已生成（`_validate_candidate` 的 report_text）但未下发 | 任一触发 `shacl_violation` 的 apply（如 `60-f16-bad`、`95-n5-violate`） | 期望：§8/F15 要求可修复错误；至少给出 focus node 与 result path。实际：调用方无法定位违例，只能逐字段试错 | §8、F15、F16 |
| D9 | Low | `update_shape` / `delete_shape` 只删除 `<shape> ?p ?o`，遗留孤儿 `sh:property` blank node 子树（实测 shapes 图中存在 2 个无主 `sh:path/sh:datatype/sh:minCount` 节点） | create → update → delete 同一 Shape 后 dump shapes 图 | 期望：删除后无残留约束节点（图 GC/审计不被污染）。实际：残留节点虽当前不被 pySHACL 选中，但属于不可控垃圾且破坏 diff/审计 | §9.1、R07 |
| D10 | Low | guidance 的 `shape_iris` 对生成 Shape 返回 blank node 标识（如 `N8c368304cce44e458cc081b98924e950`），无稳定 IRI/来源标签 | 读取多类实体的 entity-shape（`61-entitieshape-s08-multiclass.json`） | 期望：§6.1 要求来源可追踪。实际：客户端拿到不可引用的标识 | §6.1 |
| D11 | Low | `update_shape` 对不存在的 `shape_id` 直接当 upsert（无存在性校验），可能掩盖调用方拼写错误 | `update_shape shape_id=不存在` → applied | 期望：F15/§8 语义上应返回可修复错误或明确文档化 upsert。实际：静默创建 | F15、R13 |
| D12 | Medium | 实体类成员变更无 API 路径与 UI 写回：`update_entity` 白名单不含 `class_iris`（`modeling_handlers.py:140-170`，实测报 `Unknown payload field(s): class_iris`）。设计§4.3 规定成员增删走 `create_relation`/`delete_relation`（谓词 `rdf:type`），该路径实测可用，但 EntitiesPage 的多选分类没有对应的写回命令（`frontend/src/pages/EntitiesPage.tsx:373` 仅在创建载荷中携带 `class_iris`） | UI/客户端尝试修改既有实体的分类集合 | 期望：S12“EntitiesPage 可选 Class/多选分类、显示完整类别并导航”与 S03 的增加/移除成员需有用户可达路径。实际：Agent 可经 relation 命令完成，用户路径缺失 | §4.3、S03、S12 |

补充观察（不计为缺陷）：一次会话内先后出现“Shape 使既有数据违反 → 之后所有数据写入全部被拒”的连锁；这是 D2/D3 的自然后果，平台仍可通过删除对应 Shape 恢复（`95-del-*` applied），但没有任何提示指出需要删除哪个 Shape（与 D8 叠加）。

### 8.5 未执行/阻塞用例与原因

- F08：BLOCKED（D1）。合并/冲突逻辑在单元级已证明可用，产品接线使其无法经真实入口触发。
- S11、B02、B08、F03、F07、F10：NOT_EXECUTED，需 R3.0-006 授权下的真实 Team run（本轮边界禁止）。
- Q01-Q07：NOT_EXECUTED，按 §5 需 009 机械增量通过 + 006 授权 + 008B 第二段/011 依赖。
- B04、B06、B09、B11、F01/F02/F04/F05/F11/F12/F13/F14：PARTIAL，自动化/合同级证据已取得，缺少真实 run 或受保护对象负向探针。
- S12、B13、R02 的 MCP/UI 对照子项未单独取证。

### 8.6 清理与复查

| 项 | 结果 |
| --- | --- |
| 测试项目 | 本轮独立项目 `0ea43688-07ba-4537-b5a3-606a27e4219b` 及首个中止 run 的 `248e9be3-36e4-4427-a402-84a288d3b05b` 均通过 API 删除；隔离探针项目一并删除 |
| 临时目录 | `/tmp/r3009-round1/`、`/tmp/r3009-head-check`（HEAD 复核用分离工作树）在记录归档后删除 |
| 未清理项 | 无；受保护对象与他人 workspace 未触碰 |

### 8.7 本轮结论

**FAIL（ REVISE ）**。S15/S16、R01-R13、F06、B01/B05/B12 等核心兼容与边界用例通过，真实存储/真实入口证据齐全；
但 §6.1 新增 Shape 目标的产品接线（D1/D2/D3）、成员级批准合同（D4）、typed 错误出口（D5）共五项 High 缺陷直接阻塞
最低验收条件中的“三类 Shape 目标可创建且可读”、“三类批准分别生效”与“typed 可定位错误”。S08/S17 判 FAIL、F08 判 BLOCKED。
按 §6 完成门，S/B/F 三层均有缺失证据，R3.0-009 平台/流程增量未通过本轮独立测试。

---

## 9. 独立测试 Round 2（需求测试 agent，2026-09-09）

开发者声明 D1-D12 全部修复并给出新 development-ready 信号后，基于**同一份共享测试计划**执行的独立复测轮。
本节只追加，不改动 §1-§8 任何内容；未修改任何产品代码；未提交任何变更；未启动真实 `semantic modeling start`；
R2.3 旧任务未被触发为真实 run。开发方 disposition 摘要未被直接采信，全部逐条重新取证。

### 9.1 轮次信息与版本

| 项目 | 记录 |
| --- | --- |
| 被测版本 | git `cde5766` + 未提交修复批（本需求相关实现文件：`backend/app/services/modeling_handlers.py`、`semantic_command_compiler.py`、`semantic_read_model.py`、`semantic_shape_endpoint_service.py`、`semantic_shape_guidance_reader.py`、`semantic_shape_merge.py`、`semantic_sparql_templates.py`、`semantic_canonical_write.py`、`modeling_batches.py`、`modeling_team/contracts.py`、`protocol_mechanics.py`、`runner.py`、`staged_decisions.py`；相关测试/合同：`backend/tests/test_semantic_read_model_stage2_execution.py`、`backend/tests/test_r3009_unified_semantic_graph.py`、`modeling_team/tests/test_r30009_unified_graph.py`、`modeling_team/references/r3-0-009-unified-graph-contract.json`） |
| 运行时 | 与 Round 1 相同：systemd user unit `ontology-platform.service`（backend :8001，env `SEMANTIC_CANONICAL_STORE=rdf / SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary / SEMANTIC_READ_MODE=canonical`）+ vite preview :5173 + Oxigraph :7878 + PostgreSQL，全程未重启 |
| 夹具 | 独立项目 `54a6e749-f484-41ad-ab87-a380ffcbd733`（`R3009 Round2 Isolated (r3009r2-1788891636)`，owner 标注 r3009-round2-tester）+ main/cross 两个 Ontology（`2a0bb9d1-…` / `c450fe9c-…`）+ S08 补测用一次性项目 `101729d4-…`。全部写入均经真实 `POST /build-sessions/{sid}/modeling-batches`（dry_run + apply_atomic + lease），未直接注入 RDF |
| 证据 | `/tmp/r3009-round2/evidence/`（140+ 个 JSON：00-/01-/10-/20-/30-/4x-/5x-/6x-/7x-/8x-/9x-/10x-/11x-/12x-/20x- 编号 + 四套自动化输出文本）。临时目录按仓库规则在本记录归档后删除，关键回执摘录已内联到本节 |
| 复现命令 | 同 §2.3：`cd backend && uv run python -m pytest tests -q`；`cd frontend && npm run build`；`cd frontend && npx playwright test`；`uv run --project backend python -m pytest modeling_team -q`；`uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r3-0-002-modeling-team.yaml --task modeling_team/tasks/r3-0-009-unified-graph-real.yaml` |

### 9.2 自动化验证（独立复跑，非引用开发方数字）

| 命令 | Round 2 结果 | 与 Round 1 对比 |
| --- | --- | --- |
| `cd backend && uv run python -m pytest tests -q`（在 `backend/` 目录执行） | **995 passed, 36 skipped, exit 0**（55s） | 981 → 995（修复批新增 14 个用例），仍全绿 |
| `uv run --project backend python -m pytest modeling_team -q` | **1206 passed, 1 skipped, 318 subtests passed, 7 failed, exit 1**；7 个失败仍全部位于 `test_deepseek_codex_runtime.py` 的 env-file/权限参数化用例（预先存在、环境性，Round 1 已在 `cde5766` 分离工作树确认为与本需求无关） | 1205 → 1206；失败集合与 Round 1 完全一致 |
| `modeling_team/tests/test_r30009_unified_graph.py`（单独复跑） | 24 passed | 23 → 24（新增 member_relation 用例） |
| `cd frontend && npm run build` | 成功（3.87s，仅 chunk 体积告警），exit 0 | 同 Round 1 |
| `cd frontend && npx playwright test` | **39 passed（9.9s），exit 0**，含新增 `stage2-graph-derived.spec.ts › EntitiesPage edits formal class membership via rdf:type relation commands` | 38 → 39（新增 D12 相关用例） |
| `modeling_team validate --profile r3-0-002 --task r3-0-009-unified-graph-real` | exit 0，`model_profile: null` | 同 Round 1 |

### 9.3 D1-D12 修复项逐条 disposition

状态口径：**FIXED** = 有真实存储/真实入口反证消失且正向证据齐全；**STILL FAILING** = 缺陷仍可复现；
**PARTIAL** = 声明的一部分成立、另一部分不成立；**NOT REPRODUCED** = 本轮无法构造前置条件（如实声明）。

| # | 开发方声明 | Round 2 结论 | 独立取证（真实 HTTP 入口 / 真实存储） |
| --- | --- | --- | --- |
| D1 | Shape 写读统一到 `…/graph/shapes/{ont}/custom`；读失败改为向上抛 | **FIXED**（副作用引出新缺陷 D14，见 9.5） | `create_shape`（class/node/subjects-of 三种目标）apply 成功后，`GET /graph-sets/{gs}/read-models/entity-shape` 与 `GET /graph-sets/{gs}/shapes/classes/{class_iri}` 均返回该 Shape：`sources: ["custom:…/graph/shapes/{ont}/custom"]`、`provenance: "merged"`、`shape_split.{generated_subgraph,custom_subgraph}` 显式给出（`61-d1-entity-shape-dev1.json`、`62-d1-class-shape-device.json`、`93-…`、`174/175-…`）。读失败不再被吞：数据图缺失时改为 500（→ D14） |
| D2 | `_validate_candidate` 显式分 shapes 图 / 数据图（含 `/custom` 子图） | **STILL FAILING** | 修复只落在**预检路径**（`modeling_batches.py:1014-1027` 传 `candidate_graph_iris=self._data_graphs(...)`），**apply 路径**（`modeling_batches.py:1969-1983` → `apply_compiled_command`，`semantic_canonical_write.py:151-190`）仍未传 candidate，`_validate_candidate` 回退为 `delta.affected_graph_iris()`＝shapes 图（`semantic_canonical_write.py:470-500`，其 docstring 明说 “the Modeling batch passes its workspace data scope here”，但 apply 路径没传）。只读探针（`164-d2-apply-vs-preapply-validation.json`）：同一 `create_shape`（`target_node_iri=…/entity/dev-1` + `serial_no min_count=1`，数据图中该实体确有 `serial_no`）——apply 路径参数 → `conforms=false`（`MinCountConstraintComponent` 违例）；预检路径参数（数据图为候选）→ `conforms=true`。端到端后果：apply 返回 `uncertain_execution` → 批次卡 `recovering`（`202-31-d2-node-target-shape-apply.json`、`46-d2-apply-resume.json`）→ 永久写栅栏（→ D13）。带 `min_count>=1` 的 `target_node_iri` 目标 Shape **完全无法创建** |
| D3 | 绝对 IRI 的 `path_id` 原样作为 `sh:path` | **FIXED** | `create_shape` + `target_subjects_of_iri=<serial_no 绝对 IRI>` + `path_id=<同一绝对 IRI>` apply 成功（`206-70-…`）；随后实体写入正常被校验（`207-72-…` applied）；违例 `result_path`/`source_shape` 指向真实谓词 `…/property/serial_no`，不再出现 `…/property/http%3A%2F%2F…` 假谓词（`208-73-…`、`164-…`） |
| D4 | `DECISION_TARGET_KINDS` 补 `member_relation`，合同 JSON 同步 | **FIXED** | 常量与合同一致：`("commonality_node","member_relation","commonality_relation")` == `r3-0-009-unified-graph-contract.json:76`（`160-d4-member-relation-pipeline.json`）。独立重建完整闭合（candidate → projection → plan → approvals 含 `target_kind=member_relation` 决定 → 真实写出 intent/receipt → `staged_intent_receipt_issues`）：全部 0 issue；负向对照：篡改 digest → `approval_content_mismatch`，旧 revision → `approval_stale`，member_relation 带 scope → `relation_scope_ambiguous`（`161-d4-closure-digest-drift.json`） |
| D5 | 两个冲突异常 → 400 typed finding | **FIXED** | 空目标/零目标：`shape_target_conflict`，`path=["items",0,"payload","target_class_id","target_node_iri","target_subjects_of_iri"]`；`class_iri_or_legacy_id` 不在 `class_iris`：`class_membership_conflict` + 逐字段 path；HTTP 状态 200/4xx + `attempt_status=validation_failed`，**不再 500**（`10-d5a-…`、`11-d5b-…`） |
| D6 | 多目标拒绝含逐字段 path | **FIXED** | `target_class_id` + `target_node_iri` 同传：`code=shape_target_conflict`，`path=["items",0,"payload","target_class_id","target_node_iri"]`，message 保留可读说明（`12-d6-multi-target-dry_run.json`） |
| D7 | envelope 增 `{limit,returned,visible_count,has_more,truncated,complete}` | **FIXED** | `entity-list?limit=1` → `paging={"limit":1,"returned":1,"visible_count":5,"has_more":true,"truncated":false,"complete":false}`；`limit=2` → `has_more:true`；无 limit → `{"limit":500,"returned":5,"has_more":false,"truncated":false,"complete":true}`（`30-d7-entity-list-limit1/2/None.json`） |
| D8 | violation 投影补 `focus_node/result_path/component/source_shape` | **FIXED** | 触发 SHACL 违例的 apply：finding `code=shacl_violation`，`details.violations[0]` 含 `focus_node=…/entity/dev-bad`、`result_path=…/property/serial_no`、`constraint=…#MinCountConstraintComponent`、`source_shape=…/shape/r2-device-serial-shape#property-03b5e0…`、`severity` 与 message（`208-73-d8-violation-apply.json`） |
| D9 | 约束节点确定性 IRI `<shape#property-{sha256}>/list-n`，级联删除可寻址 | **FIXED**（平台写入路径） | create→update→delete 同一 Shape 后直接查存储：本测试自定义图 `…/shapes/{ont}/custom` 内 `1` 个 `sh:NodeShape`、`1` 个 `sh:property` 节点且全部可达，**孤儿约束节点 0 个**；节点形如 `…/shape/{id}#property-{64 位 hex}`，可被 delete 协议寻址。开发方声明的残余（外部手工写入的 blank-node 形状）单独核对，见 9.6 |
| D10 | 生成形状 IRI 稳定 | **FIXED** | 违例投影与 guidance 均给出确定性 IRI：自定义 `…/shape/r2-device-serial-shape#property-03b5e056…`、生成 `…/graph/shapes/{ont}/generated#Device`（`208-73-…`、`61-d1-…`、`174-…`） |
| D11 | `update_shape` 不存在 id → 404 `shape_not_found`（同批 create→update 合法） | **PARTIAL** | 前半成立：`update_shape shape_id=不存在` → `code=shape_not_found`，`path=["items",0,"payload","shape_id"]`，message 明示 “update_shape replaces an existing shape, use create_shape to define one”（`212-79-d11-unknown-update-apply.json`）。后半不成立：同批 create→update（甚至 create→update→delete 生命周期）被 `conflicting_item_effects` 拒绝（`213-80-d11-lifecycle-apply.json` 3 条 error、`214-90-d11-create-update-apply.json`），与 disposition 声明矛盾 → 新缺陷 D15 |
| D12 | 实体类成员编辑改走 `create_relation`/`delete_relation`（rdf:type）；`update_entity` 不再携带 `class_iris` | **FIXED** | 合同：`update_entity` + `class_iris` → `invalid_command_payload Unknown payload field(s): class_iris`（`246/247-155-d12-…`）。路径：`create_relation`（谓词 `rdf:type`）加成员 → read model `class_iris` 立即包含新类；`delete_relation` 移除 → 恢复 `[]`（`220-…`/`221-…`/`222-…`、`238-…`/`239-…`/`240-…`、`152/154-s03-…`）；删除约束 Shape 后同样可用（`243/244/245-…`）。UI：新增 Playwright 用例 `EntitiesPage edits formal class membership via rdf:type relation commands` 通过（39 passed 内） |

### 9.4 逐用例状态（Round 1 FAIL/BLOCKED/PARTIAL 复测 + 受影响回归）

| ID | Round 1 | Round 2 | 证据与说明 |
| --- | --- | --- | --- |
| S08 | FAIL | **PASS** | 一次性项目 `101729d4-…`（前一轮夹具项目已在清理步删除）：Device、Asset 各建自定义 Shape（`target_class_id` + `min_count=1`，均 applied），`create_entity class_iris=[Device,Asset]` applied，`entity-shape` 返回**两个**字段：`asset_tag`（`matched_targets=[{kind:class, value:…/Asset}]`）与 `serial_no`（`…/Device`），`sources` 均为 `custom:…/shapes/{ont}/custom`；`class-shape(Device)`/`class-shape(Asset)` 各返回自身字段（`183-s08-entity-shape-multiclass.json`、`184-s08-class-shape-*.json`）。多类实体的自定义 Shape 不再丢失 |
| S17 | FAIL | **STILL FAILING** | class 目标与 subjectsOf 目标可创建、可读且参与真实校验（`204-51-…`、`206-70-…`、`207-72-…`、`61/62-…`）；但 **node 目标 + `min_count>=1` 一律无法 apply**（D2 未修），`sh:targetNode` 最常用路径仍被阻断（`202/46-…`） |
| B03 | FAIL | **PASS** | 见 D7：`limit=1/2/未传` 的窗口元数据齐全，`visible_count` 相对授权可见集合，`has_more/complete` 明确区分窗口与全集（`30-d7-*.json`） |
| F08 | BLOCKED | **STILL FAILING**（由 BLOCKED 变为可复现的 FAIL） | 自定义 Shape 现已进入 guidance，冲突场景**可达**：对同一 Class（Asset）先后创建 `asset_tag min_count=1` 与 `min_count=2` 两个自定义 Shape（均 applied），`class-shape(Asset)` 返回 **200 + 单个合并字段（min_count=2）**，未返回 409/`shape_conflict`（`101-f08-asset-class-true-conflict.json`；非冲突对照 `96-f08-asset-class-shape.json` min_count=1）。根因在 `extract_shape_guidance_for_class` 的“同 path 后写覆盖”先于 `merge_shape_guidance` 的冲突检测执行，`shape_conflict` 分支实际不可达。语义上等于“后提交者静默覆盖既有约束” |
| S03 | PASS | **PASS**（回归） | rdf:type relation 加/删成员往返一致；删除约束 Shape 后仍可用（`220-…`~`222-…`、`238-…`~`240-…`、`243-…`~`245-…`、`152/154-…`） |
| S12 | PARTIAL | **PASS** | 读侧 `class_iris` 展示 + 写侧 rdf:type relation 命令路径 + 新增 Playwright 用例通过；D12 的 UI 缺口已闭合 |
| S15 / S16 | PASS | **PASS**（回归） | 缺 lease_token 的 `apply_atomic` 与 stale `expected_workspace_version` 均返回 typed 4xx（`112-s15-no-lease.json`、`113-s16-stale-version.json`） |
| B01 | PASS | **PASS**（回归） | class 成员冲突 → `class_membership_conflict` + 逐字段 path（`11-d5b-…`），不再 500 |
| B10 | PARTIAL | **PASS**（回归） | `class_iris` 重复/乱序归一化后 `class_iris=['…/Device']`；scalar+array 冲突 typed 拒绝（`223/230/236-109/126/146-b10-dups`、`110/127/147-b10-…`、`224/231-111-…`） |
| B06 | PARTIAL | **PASS**（部分） | project 级 Graph Set 同时纳入两个 Ontology 的 named graph 后，entity-list 同时返回两侧实体 + `paging` 元数据（`128-b06-cross-graph-set.json`、`129-b06-cross-entity-list.json`） |
| F15 | PARTIAL | **PASS**（除 S17 的 D2 阻断） | 空/零/多目标 typed 拒绝（`10/11/12-…`）；相对 IRI 拒绝与越权引用仍由既有用例覆盖；node 目标 apply 被阻断归 D2 |
| F16 | PARTIAL | **PASS** | 违例定位字段齐全（见 D8）；“冲突不被 guidance 掩盖”仍不成立（归 F08） |
| R01 / R13 | PASS | **PASS**（回归） | 旧 `target_class_id` Shape 创建/读取正常（`204-51-…` applied、`96-…` 200）；未知 payload 字段拒绝：`invalid_command_payload Unknown payload field(s): shape_graph_iri`（`242-149-r13-unknown-field-dry_run.json`）；`update_entity` 拒绝 `class_iris`（`246/247-…`） |
| R02 | PASS | **PASS**（回归） | `class_iri`（标量）+ `class_iris`（数组）双投影并存，detail/list 路由正常（`130-r02-dev1-detail.json`、`148-r02-dev1-detail.json`） |
| R03 | PASS | **PASS**（回归） | item payload 携带 `ontology_id`/`graph_set_id` → `forbidden_target_override`（`114-r03-forbidden.json`） |
| F08 之外的 Round 1 PARTIAL（S09/S10/B04/B06/B08/B09/B11/B13/F01/F02/F04/F05/F09/F11-F14 等） | PARTIAL | **维持** | 本轮优先级为 D1-D12 复测与受影响回归；未新增真实 Team run（R3.0-006 授权仍未开放），无新证据，不重复罗列 |

### 9.5 缺陷清单（Round 2 新增 + 遗留）

| # | 严重度 | 缺陷 | 复现（真实入口） | 期望 / 实际 | 证据 |
| --- | --- | --- | --- | --- | --- |
| D13 | **High**（新） | Shape apply 失败把 Ontology 永久锁死，且无任何 API 出口：apply 校验失败 → `uncertain_execution` → 恢复观测读 `…/shapes/{ont}/custom` 时因该图尚未物化而抛错 → `recovery.observation={state:"unexpected",reason:"rdf_observation_failed"}` → `recovery_requires_intervention`、`safe_to_retry:false` → 写栅栏永不释放。之后该 Ontology 上**任何**批次都返回 `409 {"code":"ontology_write_fenced","message":"Ontology has an in-flight Modeling Batch write"}`；系统无释放栅栏/删除卡死批次的接口（恢复协议依赖的 RDF 观测正是失败点，形成死锁） | ① 任一 `create_shape`（`target_node_iri` + `min_count>=1`，D2 触发）；② 之后对该 Ontology 再提交任意批次（dry_run 亦然） | 期望：可恢复失败不得永久剥夺写权限；`safe_to_retry` 或人工出口必须可用（§3.3、F07/F09 恢复语义）。实际：批次永久 `recovering`，Ontology 永久 fenced，唯一出路是弃用该 Ontology（本轮因此把后续用例迁到第二个夹具 Ontology） | `202-31-d2-…`、`46-d2-apply-resume.json`（`recovery` 全文）、`162-d13-batch-state.json`（次日仍 `batch_status=recovering`）、`163-d13-write-fence-error.json`（409 全文） |
| D14 | **High**（新） | `GET /graph-sets/{gs}/read-models/entity-shape` 在“`…/shapes/{ont}/custom` 已物化但 `…/data/{ont}` 尚未物化”时返回 **500 "Internal Server Error"**：`semantic_shape_endpoint_service.py` 的 `_load_graph`（数据图路径）直接抛 `RdfStoreUnavailable`，无 `_load_optional_graph` 兜底。fresh workspace（数据图懒物化）+ 先建 Shape 的合法顺序即可触发 | ① 新 Ontology；② `create_shape`（物化 custom 图）；③ `GET …/read-models/entity-shape?entity=…` | 期望：缺图应等价于“该图无数据”，返回空 `fields`（200），与 shapes 图的 `_load_optional_graph` 行为一致。实际：500，无 typed 错误、无 code/path | `52-d1-entity-shape-dev1.json`（status 500 全文）；对照同请求在数据图物化后为 200（`61-…`） |
| D15 | **Medium**（新） | 同一批次内对同一 Shape 先 `create_shape` 再 `update_shape` 被 `conflicting_item_effects`（“Items contain incompatible writes to the same semantic target”）拒绝；D11 disposition 声明“同批 create→update 合法”，实现与声明不一致；且 `backend/tests/test_modeling_batches_service.py` 只覆盖“未知 id”分支，没有 create→update 兄弟用例 | 同批 items：`create_shape shape_id=X` + `update_shape shape_id=X`（apply_atomic） | 期望：与 D11 声明一致——create 使 update 合法（同一批内可定义并细化一个 Shape）。实际：`attempt_status=validation_failed`，3 条 `conflicting_item_effects` error。当前只能拆成两批绕过 | `213-80-d11-lifecycle-apply.json`、`214-90-d11-create-update-apply.json`（findings 摘录见 9.3 D11 行） |
| D2 | **High**（遗留） | 见 9.3：apply 路径仍以 shapes 图为 SHACL 候选数据 | | | `164-…`、`202-…`、`46-…` |
| F08 | **High**（遗留，由 BLOCKED 转 FAIL） | 同 path 多个自定义 Shape 静默“后写覆盖”，`shape_conflict` 不可达 | | | `101-…`、`96-…` |

### 9.6 开发方残余声明核对

| 声明 | 核对结论 |
| --- | --- |
| “D9 只覆盖平台写入的 IRI 形状；外部手工写入 `/custom` 的 blank-node 形状无法被删除协议寻址（需可 join 的删除协议，未纳入本轮）” | **属实，且已在存储中观察到实例**：直接查询 Oxigraph 发现 `…/graph/shapes/5ac4dbb7-1bd2-412d-b47f-6d00f85b79f0`（其 Ontology 行已被删除，API 404）含 **17 个孤儿 blank-node 约束节点**（`sh:path` 存在但不可从任何 `sh:NodeShape` 经 `sh:property` 到达，全部 `bnode:true`）。对比之下，本测试平台写入并删除后自建的 `…/shapes/c450fe9c-…/custom` 内孤儿节点为 **0**。附带观察：Ontology 删除并不清理其 shapes 图，残留图仍留在存储中（与 9.8 清理缺口同源） |
| “`source_shape` 在旧 bnode 形状上仍是 bnode 标签” | **属实（代码路径一致）**：确定性 IRI 只对平台写入的形状生成（`semantic_command_compiler.py` 的 `_shape_node_digest`/`property-{digest}`）；本轮无旧版 bnode 形状 fixture 可用，未单独复现（**NOT REPRODUCED**，不影响判定） |
| 其余 disposition（D1、D3-D12 的声明部分） | 与独立取证一致；唯 D11 的“同批 create→update 合法”与 D2 的隐含“apply 也可用”不成立，见 9.3/9.5 |

### 9.7 未执行/阻塞用例与原因

- S11、B02、B08、F03、F07、F10：NOT_EXECUTED，仍需 R3.0-006 授权下的真实 Team run（本轮边界禁止；与 Round 1 相同）。
- Q01-Q07：NOT_EXECUTED，按 §5 仍需 009 机械增量通过 + 006 授权 + 008B 第二段/011 依赖。
- B04、B09、B11、B13、F01/F02/F04/F05/F09/F11-F14：维持 PARTIAL，未新增证据（本轮未构造受保护对象负向探针或真实 run）。
- 受 D13 影响的“同一 Ontology 上的后续用例”：改在第二个夹具 Ontology（cross）与一次性项目上执行，未当作 PASS 处理。

### 9.8 清理与复查

| 项 | 结果 |
| --- | --- |
| 测试项目 | `54a6e749-f484-41ad-ab87-a380ffcbd733`（Round 2 主夹具）与 `101729d4-2ddb-433c-abf9-d143e03d9f0a`（S08 一次性夹具）均 `DELETE /projects/{id}` → **204**，复查 GET → 404 |
| 临时目录 | `/tmp/r3009-round2/`（driver/stage 脚本、evidence、state）在本记录归档后删除 |
| 未清理项 | **5 个 Graph Set 无法删除**：平台没有 `DELETE /semantic/graph-sets/{id}`（实测 **405 Method Not Allowed**，代码中该路由不存在），项目删除也不级联清理 Graph Set，导致 `6e69d516-609a-58f6-aabb-788c53896b7e`、`c48e189c-8e0f-50d3-8225-1d87958f7d2e`、`b1e59dc6-90dc-4b8d-8d75-deb7f69e10c7`、`47bbde44-e575-5016-94f1-5b4dc706c36d`、`a9f23531-0ae6-52f9-8c4d-df7a4e2c87cc` 残留且 `scope_id` 悬空（指向已删项目）。它们只含本测试的语义资源（class/entity/shape），不含客户/工单等业务数据，也无权限暴露；但“测试夹具不可自清理”与 `ontology_write_fenced`（D13）叠加会让隔离测试持续消耗 Ontology 名额，建议补 Graph Set/Ontology 生命周期接口或级联删除 |
| 其他 | 未触碰他人 workspace 与受保护对象；未改产品代码；未 git commit |

### 9.9 本轮结论

**FAIL（ REVISE ）**。修复批确有实质进展：D1/D3/D4/D5/D6/D7/D8/D9/D10/D12 十项经真实入口+真实存储复验为 FIXED，
S08、B03 由 FAIL 转 PASS，Round 1 的 500 型错误出口全部变为 typed finding，四套自动化独立复跑结果与开发方数字一致
（backend 995 passed / playwright 39 passed / build 成功 / modeling_team 仅 7 个已知环境性失败，009 用例 24 passed）。

但仍有两类问题阻塞验收：
1. **D2（High，遗留）**：apply 路径仍把 shapes 图当作 SHACL 候选数据，`target_node_iri` + `min_count>=1` 的 Shape 无法创建（S17 仍 FAIL）；
2. **新缺陷 D13/D14（均 High）**：失败的 Shape apply 会把 Ontology 永久锁死且无恢复出口；`entity-shape` 在合法的“先 Shape 后数据”顺序下返回 500。另有 D15（Medium）与 D11 声明不一致，F08 由 BLOCKED 转为可复现的 FAIL（`shape_conflict` 仍不可达）。

按 §6 完成门，“三类 Shape 目标可创建且可读”（S17）、“多 Shape 冲突显式上报”（F08）与“失败可恢复、可定位”（D13/D14）仍未满足，
R3.0-009 平台/流程增量未通过本轮独立测试。建议开发 agent 先修 D2（apply 路径传 `candidate_graph_iris=data 图`）、
D13（恢复观测对缺省图容错 + 提供栅栏/恢复出口）、D14（数据图改用 optional 读取），并补 D15 的 create→update 用例与 F08 的冲突检测接线，再进入 Round 3。

## 10. 独立测试 Round 3（需求测试 agent，2026-09-09）

开发方声明 Round 2 全部缺陷（D2/D13/D14/F08/D15）已修复并给出新 development-ready 信号后，基于**同一份共享测试计划**执行的独立复测轮。
本节只追加，不改动 §1-§9 任何内容；未修改任何产品代码；未提交任何变更；未启动真实 `semantic modeling start`；
R2.3 旧任务未被触发为真实 run。开发方 disposition 摘要未被直接采信，全部逐条重新取证（代码定位 + 真实 HTTP 入口 + 真实 Oxigraph 存储）。

### 10.1 轮次信息与版本

| 项目 | 记录 |
| --- | --- |
| 被测版本 | git `cde5766` + 未提交 Round 3 修复批（本需求相关：`backend/app/services/modeling_batches.py`、`semantic_canonical_write.py`、`semantic_shape_endpoint_service.py`、`semantic_shape_guidance_reader.py`、`semantic_read_model.py`、`modeling_handlers.py`、`semantic_command_compiler.py`、`semantic_shape_merge.py`、`semantic_sparql_templates.py`、`semantic_shape_generator.py`、`backend/app/api/{schemas.py,semantic.py}`；相关测试 `backend/tests/test_modeling_batches_service.py`、`test_semantic_canonical_write_stage2.py`、`test_r3009_unified_semantic_graph.py` 等） |
| 运行时 | 与 Round 1/2 相同：systemd user unit `ontology-platform.service`（backend :8001，env `SEMANTIC_CANONICAL_STORE=rdf / SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary / SEMANTIC_READ_MODE=canonical`）+ vite preview :5173 + Oxigraph :7878 + PostgreSQL，全程未重启 |
| 夹具 | 独立项目 `da89243a-c5b5-4a5a-90db-94b593a86b2a`（run_tag `r3009r3-1788897043684`）+ main/cross 两个 Ontology（`3dbc5015-…` / `65613687-…`）+ 两个默认 Graph Set（`cf4bca22-…` / `8d6daf27-…`）+ build session `def9d50e-…`。全部写入均经真实 `POST /build-sessions/{sid}/modeling-batches`（dry_run + apply_atomic + ontology lease），未直接注入 RDF |
| 证据 | `/tmp/r3009-round3/evidence/`（139 个 JSON（001-173 编号）+ 5 个自动化输出文本）。临时目录按仓库规则在本记录归档后删除，关键回执摘录已内联到本节 |
| 复现命令 | 同 §2.3：`cd backend && uv run python -m pytest tests -q`；`cd frontend && npm run build`；`cd frontend && npx playwright test`；`uv run --project backend python -m pytest modeling_team -q`；`uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r3-0-002-modeling-team.yaml --task modeling_team/tasks/r3-0-009-unified-graph-real.yaml` |

### 10.2 自动化验证（独立复跑，非引用开发方数字）

| 命令 | Round 3 结果 | 与 Round 2 对比 |
| --- | --- | --- |
| `cd backend && uv run python -m pytest tests -q`（在 `backend/` 目录执行） | **1006 passed, 36 skipped, exit 0**（59.8s） | 995 → 1006（修复批新增 11 个用例），仍全绿 |
| `backend/tests/test_r3009_unified_semantic_graph.py`（单独复跑） | 29 passed；`test_semantic_read_model_stage2_execution.py` + `test_semantic_canonical_write_stage2.py` 合计 46 passed | Round 2 未单列 |
| `uv run --project backend python -m pytest modeling_team -q` | **1206 passed, 1 skipped, 318 subtests passed, 7 failed, exit 1**；7 个失败全部位于 `test_deepseek_codex_runtime.py`（env-file/权限参数化用例）。本轮在 **干净 `cde5766` 的 detached worktree**（`/tmp/r3009-head-wt`，用后即删）单独复跑该文件：**同样 7 failed / 14 passed**，证明与本需求修复批无关，属本机环境性失败（本机存在真实凭据 fallback 文件，运行时不进入不安全分支） | 与 Round 2 完全一致（1206 passed / 7 failed） |
| `modeling_team/tests/test_r30009_unified_graph.py`（单独复跑） | 24 passed | 同 Round 2 |
| `cd frontend && npm run build` | 成功（4.14s，仅 chunk 体积告警），exit 0 | 同 Round 2 |
| `cd frontend && npx playwright test` | **39 passed（10.2s），exit 0** | 同 Round 2 |
| `modeling_team validate --profile r3-0-002 --task r3-0-009-unified-graph-real` | exit 0，`model_profile: null` | 同 Round 2 |

### 10.3 Round 2 缺陷修复项逐条 disposition

状态口径同 §9.3。

| # | 开发方声明 | Round 3 结论 | 独立取证（真实 HTTP 入口 / 真实存储） |
| --- | --- | --- | --- |
| D2 | `apply_compiled_command` 新增 `candidate_graph_iris`，apply 路径传 `self._data_graphs(ont)`（`modeling_batches.py:2034`） | **FIXED** | 代码定位：apply 路径 `apply_compiled_command(..., candidate_graph_iris=self._data_graphs(batch.ontology_id), created_shape_iris=self._batch_created_shape_iris(commands), ...)`（`modeling_batches.py:2034-2035`），预检路径同参（`:1078`）。端到端：`target_node_iri=…/entity/dev-1` + `serial_no min_count=1`（数据图中该实体确有 `serial_no`）的 Shape **apply 成功**（`020-s17-node-shape-apply.json`），`entity-shape` 返回该自定义 Shape（`021-s17-entity-shape.json`，`shape_iris` 含 `…/shape/r3-node-target-shape`）；同批次的 class 目标 `r3-device-serial-shape` 亦 applied（`030-…`）。Round 2 的“预检 conforms=true / apply conforms=false”分歧消失 |
| D13 | ① apply 定向捕获 `CanonicalShaclViolation`/`CanonicalSemanticWriteError` → 回滚 → `_fail_attempt_without_side_effects`；② `_load_observed_graphs` 缺图=空图 + `before_graph_hashes`；③ 有界恢复出口 `safe_to_retry` 随可调和性取值 | **FIXED**（确定性路径端到端验证；“不确定”路径见 10.7 的诚实声明） | 代码定位：`except (CanonicalShaclViolation, CanonicalSemanticWriteError)`（`modeling_batches.py:2042`）→ `rollback()` → `_fail_attempt_without_side_effects`（`:2806`：`recovery_state="failed_without_side_effects"`、`safe_to_retry: True`、**删除 `OntologyWriteFenceModel`**）；全文件仅剩一处 `uncertain_execution`（`:2141`，通用异常分支）。端到端：对真实数据违例（`dev-bad` 无 `serial_no`）apply → `attempt_status=validation_failed`、`recovery={"state":"not_required","safe_to_retry":false,"detail":{"history":[]}}`（无 `uncertain_execution` 历史），attempt 探针 `batch_status=open`、**写栅栏字段为空**（`031-dev-bad-apply.json`、`032-dev-bad-attempt.json`）；修正后重试 `applied`（`033-dev-good-apply.json`）；随后同 Ontology 任意批次照常 `applied`，无 `ontology_write_fenced`（`022-fence-probe-apply.json`）。另核对“真实数据违例仍被拒”：带 `min_count=2` 的自定义 Shape 在已有 1 个取值的实例上被 `shacl_violation` 拒绝（`041-f08-shape-b-apply.json`），未因 D2/D13 放行。恢复观测代码核对：`_load_observed_graphs`（`:2361`）对 `graph_exists=false` 的图返回空 `Graph` 且不再调用 `get_graph`，`before_graph_hashes` 以 plan 快照兜底合并（`:2417`），有界恢复出口 `safe_to_retry=reconcilable`（`:2167-2185`）；对应单测在 1006 passed 内（`test_apply_failure_recovers_releases_the_fence_and_is_retryable`、`test_recovery_observation_treats_a_missing_graph_as_empty`、`test_bounded_recovery_can_fail_when_no_side_effects_are_proven`、`test_recovery_stops_for_rdf_state_outside_the_persisted_plan`，单独抽取 `-k "recovery or fence or shacl or uncertain or missing_graph"` → 9 passed） |
| D14 | `_load_graph_or_empty` + envelope 增 `missing_graph_iris` | **FIXED** | 代码定位：`semantic_shape_endpoint_service.py:278` `_load_graph_or_empty(graph_iri, *, missing)`；entity 条目与 class envelope 均带 `missing_graph_iris`，另新增 `custom_graph_iris` 与 `shape_split.custom_subgraphs`。端到端：fresh workspace（仅建 class+shape、数据图未物化）`GET …/read-models/entity-shape` → **200**，`missing_graph_iris=["…/graph/data/{ont}","…/graph/ontology/{ont}"]`、`fields` 含自定义 Shape 字段（`001-d14-fresh-entity-shape.json`）；Round 2 的精确复现（cross Ontology：class+shape 已写、零实体）同样 200（`081-d14-shape-without-data.json`）；class 分支 `GET …/shapes/classes/{iri}` → 200 且返回 `min_count=1` 字段（`002-…`、`082-d14-class-shape-without-data.json`）。Round 2 的 500 不再出现 |
| F08 | `extract_shape_guidance_for_class` 按 (path, source shape) 保留多条约束并标 `source_shape_iri`；类分支 409 `shape_conflict`；endpoint 用 `merge_shape_guidance_multi` | **FIXED**（新增 Low 可诊断性缺口 D16，见 10.5） | 代码定位：`semantic_shape_guidance_reader.py:53/119` `field["source_shape_iri"]=str(shape)`；endpoint `merge_shape_guidance_multi`（`semantic_shape_endpoint_service.py:30/122/235`）；read model `code="shape_conflict"`（`semantic_read_model.py:44`，raise `:780/:810`）。端到端（无实例类 FenceProbe，两个自定义 Shape 均可合法 apply）：`min_count=1` 与 `min_count=2` 两个 Shape 先后 applied（`050/051-f08p-shape-*.json`）→ `GET …/shapes/classes/FenceProbe` 返回 **409**，`detail` 逐侧给出 `min_count=1` 与 `min_count=2`（`052-f08p-class-shape.json`）；删除其一恢复 200 单字段（`054-f08p-after-del-b.json`），再删另一恢复 200 空字段（`056-f08p-after-del-a.json`）。Round 2 的“后写静默覆盖、`shape_conflict` 不可达”不再成立。附带确认：与真实数据冲突的 Shape 仍被 apply 拒绝（`041-…` `shacl_violation`），冲突检测未被绕过 |
| D15 | `_ordered_shape_refinement` 豁免「同 shape_iri create+update 且依赖已声明」；无声明顺序仍冲突 | **FIXED**（docstring 与实现不一致记 Low D17） | 代码定位：`modeling_batches.py:949-990` 要求 kinds == `{create_shape, update_shape}`、同 `compiled.metadata["shape_iri"]`、且 `_depends_transitively` 任一方向成立。端到端：①同批 `create_shape` + `update_shape`（带 `depends_on`）→ **applied**，`class-shape` 返回细化后的 `datatype=xsd:string`（`060/070-d15-ordered-*.json`、`061-d15-after-ordered.json`）；②同批无 `depends_on` → `conflicting_item_effects`（`062/071-d15-unordered-*.json`）；③声明顺序反转（update 在前 + `depends_on`）→ applied（`091-d15c-reversed-apply.json`），与 docstring「update 先于 create 仍拒绝」不符（见 10.5 D17）。Round 2 的“同批 create→update 一律 `conflicting_item_effects`”不再成立，D11 声明与实现一致 |

### 10.4 逐用例状态（优先复测项 + 受改动影响的回归）

| ID | Round 2 | Round 3 | 证据与说明 |
| --- | --- | --- | --- |
| S17 | STILL FAILING（D2） | **PASS** | node 目标 Shape（`target_node_iri` + `min_count=1`）apply 成功并进入 guidance（`020-…`、`021-…`）；class 目标 `030-…` applied；三类 Shape 目标（class/node/subjectsOf，subjectsOf 已在 Round 2 验证）均可创建、可读、参与真实校验 |
| F08 | STILL FAILING | **PASS** | 见 10.3 F08 行：冲突可达且显式 409 `shape_conflict`，删除其中一个 Shape 后恢复 |
| F16 | PASS | **PASS**（回归，重点复测） | 违例投影含 `focus_node/result_path/constraint/source_shape/severity`：`source_shape=…/shape/r3-device-serial-shape#property-{64 hex}`（确定性 IRI，D10）（`031-dev-bad-apply.json`）；“真实数据违例仍被拒”另见 10.3 D13 行 |
| F06 / F07（恢复语义相关） | F07 NOT_EXECUTED | **PASS**（可执行部分）/ **NOT_EXECUTED**（真实 run 部分） | 失败 attempt 不再进入 `recovering`（`recovery.state=not_required`），Ontology 无写栅栏，修正批次可继续 apply（`031/032/033/022-…`）；栅栏/恢复出口的存在性由代码 + 单测（9 passed）复核。依赖真实 Team run 的 F07 部分仍受 R3.0-006 授权限制 |
| D15 场景（create→update） | —（Round 2 缺陷） | **PASS** | 见 10.3 D15 行：带声明顺序 applied、无声明顺序仍冲突 |
| D14 场景（缺图读） | —（Round 2 缺陷） | **PASS** | 见 10.3 D14 行：entity/class 两分支均 200 + `missing_graph_iris` |
| S08 | PASS | **PASS**（回归） | 多类实体聚合两个类的自定义 Shape：`class_iris=[Asset,Device]`，字段 `serial_no`/`asset_tag` 各带正确 `source_shape_iri`（`101-s08-multiclass-apply.json`、`102-s08-entity-shape.json`） |
| S03 / D12 | PASS | **PASS**（回归） | `create_relation`（rdf:type）加成员 → `class_iris=[Asset,Device]`；重复 add 幂等（再次 applied）；`delete_relation` 移除 → 恢复 `[Device]`（`151/152/153/154/155-…`）；`update_entity` + `class_iris` → `invalid_command_payload Unknown payload field(s): class_iris`（`132-d12-class-iris-apply.json`）。附带观察：类上存在与实体数据冲突的自定义 Shape 时，成员变更会被 `shacl_violation` 拒绝（`141-s03-add` 首次尝试，`140-…` 删除该 Shape 后成功）——属预期校验语义，非缺陷 |
| B01 | PASS | **PASS**（回归） | `class_iri_or_legacy_id` 不在 `class_iris` → `class_membership_conflict`，`path=["items",0,"payload","class_iri_or_legacy_id","class_iris"]`（`156-b01-conflict-apply.json`） |
| B03 / D7 | PASS | **PASS**（回归） | `limit=2` → `paging={"limit":2,"returned":2,"visible_count":6,"has_more":true,"truncated":false,"complete":false}`；无 limit → `{"limit":500,"returned":4,…,"complete":true}`（`137-d7-paging.json`、`034-entity-list-after-f16.json`） |
| B10 | PASS | **PASS**（回归） | `class_iris=["Device","Device","…/class/Device"]` 归一化为单个 `…/class/Device`（`134/135-b10-…`） |
| R13 / R03 | PASS | **PASS**（回归） | 未知 payload 字段 `shape_graph_iri` → `invalid_command_payload`（`133-r13-unknown-apply.json`）；item 级 target override 仍拒绝（Round 2 证据维持） |
| S15 / S16 | PASS | **PASS**（回归） | 本轮实测到 `lease_token_invalid` 的 typed 409（stale token，与 `lease_expired` 区分明显）；stale `expected_workspace_version` 走 409 + `current_workspace_version` 收割路径，每条批次链路均实际触发 |
| D9 / D10 | PASS | **PASS**（回归，存储级） | 本轮 create→update→delete 多轮后直接查 Oxigraph：本测试 custom 图内 3 个 `sh:NodeShape`、每个 1 个 `sh:property`，**孤儿约束节点 0 个**；约束 IRI 均为 `…#property-{64 位 hex}`（stage_g SPARQL 输出，摘录见 10.8） |
| F08 之外的 Round 1/2 PARTIAL（S09/S10/B04/B06/B08/B09/B11/B13/F01/F02/F04/F05/F09/F11-F14 等） | 维持 | **维持** | 本轮优先级为 Round 2 缺陷复测与受影响回归；未新增真实 Team run（R3.0-006 授权仍未开放），无新证据，不重复罗列 |

### 10.5 缺陷清单（Round 3 新增 + 遗留）

| # | 严重度 | 缺陷 | 复现（真实入口） | 期望 / 实际 | 证据 |
| --- | --- | --- | --- | --- | --- |
| D16 | **Low**（新） | `shape_conflict` 的 `detail` 可诊断性不足：① code 前缀重复（“shape_conflict: shape_conflict: …”）；② 冲突两侧都只报**同一 graph IRI**（`custom:…/shapes/{ont}/custom`），而不是两个冲突 **Shape IRI**（如 `…/shape/r3-f08p-a` 与 `…/shape/r3-f08p-b`），仅凭 message 无法区分是哪两个 Shape 冲突（guidance 条目里的 `source_shape_iri` 是正确的） | 对同一无实例类先后建 `min_count=1`、`min_count=2` 两个自定义 Shape，`GET …/shapes/classes/{iri}` | 期望：409 一次、message 明确列出两侧 shape IRI 与各自约束。实际：409 正确，但 detail 重复前缀且两侧同图名，Shape 级归因丢失 | `052-f08p-class-shape.json`：`"shape_conflict: shape_conflict: path …/property/serial_no is constrained differently by custom:…/custom (min_count=1) and custom:…/custom (min_count=2); align the shapes or split the target"` |
| D17 | **Low**（新，文档/实现不一致） | `_ordered_shape_refinement` docstring 写“update_shape 先于其 create_shape 仍被拒绝”，但实现按**任一方向**的传递依赖豁免（`_depends_transitively(left,right) or _depends_transitively(right,left)`），端到端也确实 applied | 同批 items：`update_shape`（带 `depends_on: [create 的 client_item_id]`）在前、`create_shape` 在后 | 期望：文档与实现一致。实际：行为比文档宽（反向声明顺序也放行）。不构成安全/正确性问题（两者都需要显式声明顺序），建议改 docstring 或收紧实现 | `091-d15c-reversed-apply.json`（applied）；`modeling_batches.py:949-990` |
| D18 | **Low**（遗留，Round 2 §9.8 已记录为清理缺口） | 项目删除不级联清理 Graph Set，Ontology 删除不清除其 RDF named graph：本轮夹具项目 `DELETE /projects/{id}` → 204、project/ontology GET 均 404，但 **2 个 Graph Set 仍列出且 `scope_id` 悬空**（指向已删 Ontology），Oxigraph 仍留 **4 个 named graph**（main 的 data/ontology/shapes-custom 与 cross 的 ontology） | 建项目 → 建 Ontology/Graph Set → 写入 → 删除项目 → 查 `/semantic/graph-sets` 与 Oxigraph `SELECT DISTINCT ?g` | 期望：删除项目后其 Graph Set 与 named graph 一并清理（或提供显式删除接口）。实际：残留成为新的孤儿（与 Round 2 的 5 个同类） | `170-project-delete.json`（204）、`171-project-after-delete.json`（404）、`172-graph-set-list-after-delete.json`（2 个 Graph Set 仍在）、`173-store-graphs-after-delete.json`（4 个 graph IRI） |
| D2 / D13 / D14 / D15 / F08 | —（Round 2 缺陷） | **全部关闭**：本轮独立取证未再复现（见 10.3） | | | |

### 10.6 开发方残余声明核对

| 声明 | 核对结论 |
| --- | --- |
| 「Round 2 遗留的 5 个测试 Graph Set 已凭归属证明经 repository/store 层删除，复核 0 残留」 | **属实**：`GET /semantic/graph-sets?limit=500` 返回 781 条，逐条比对 `6e69d516-…`、`c48e189c-…`、`b1e59dc6-…`、`47bbde44-…`、`a9f23531-…` 均不存在；Oxigraph 全部 named graph（33 个）中也无任何携带这 5 个 id 的 graph IRI（`160-graph-set-list.json`、`002-161-store-graph-iris.json`）。注意：这 5 条是**人工清理**，D18 的系统性缺口仍在（见 10.5，本轮又新增 2 条同类孤儿） |
| 「backend 1006 passed / playwright 39 / build 成功 / validate exit 0 / 服务健康」 | **一致**：1006 passed + 36 skipped / 39 passed / build exit 0 / validate exit 0 且 `model_profile: null`；backend :8001、frontend :5173、Oxigraph :7878 均 200，`ontology-platform.service` active |
| 「modeling_team 1213 passed」 | **不完全一致但无实质影响**：独立复跑为 **1206 passed / 1 skipped / 7 failed**；7 个失败与 Round 2 完全相同，且本轮在干净 `cde5766` worktree 复现同样失败，证明与本需求无关（环境性）。差异来自统计口径（passed+skipped）与是否计入已知失败 |
| 其余 disposition（D2/D13/D14/F08/D15 的声明部分） | 与独立取证一致；唯 D13 的「有界恢复出口 `safe_to_retry` 取值变化」属行为变更点，其“drifted 仍 fenced、reconcilable 释放”的语义由单测覆盖（见 10.3），本轮无法在共享基础设施上做故障注入实测（见 10.7） |

### 10.7 未执行/阻塞用例与原因

- S11、B02、B08、F03、F07（真实 Team run 部分）、F10：NOT_EXECUTED，仍需 R3.0-006 授权下的真实 Team run（本轮边界禁止；与 Round 1/2 相同）。
- Q01-Q07：NOT_EXECUTED，按 §5 仍需 009 机械增量通过 + 006 授权 + 008B 第二段/011 依赖。
- **D13 的「不确定执行 → recovering → 恢复结论 → 栅栏解除 → 安全重试」全链路未做线上故障注入**：该链路只能由“写入中途的非确定性异常”触发（`modeling_batches.py:2141` 的通用异常分支），在共享基础设施上人为制造 store 中途故障需改动产品代码或破坏共享存储，超出本轮边界。已用两类替代证据闭合：①确定性拒绝路径的端到端反证（失败不再进入 `recovering`、无栅栏、重试成功，`031/032/033/022-…`）；②该链路的单测覆盖在 1006 passed 内独立复核（4 个用例按 `-k` 单独抽取 → 9 passed）。此替代不放宽 §3.3 验收：真实 run 依赖的部分仍归 F07/F10 的 NOT_EXECUTED。
- B04、B09、B11、B13、F01/F02/F04/F05/F09/F11-F14：维持 PARTIAL，未新增证据。

### 10.8 清理与复查

| 项 | 结果 |
| --- | --- |
| 测试项目 | `da89243a-c5b5-4a5a-90db-94b593a86b2a` `DELETE /projects/{id}` → **204**，复查 GET → **404**；两个 Ontology `GET /semantic/ontologies/{id}` → **404** |
| 夹具残留 | 本轮 batch 产物已全部随项目删除；存储级 custom 图在删除前复核：3 个 `sh:NodeShape`（`r3-node-target-shape`、`r3-device-serial-shape`、`r3-s08-device-shape`）、**孤儿约束节点 0**；删除后（见 D18）Oxigraph 仍留 4 个 named graph、2 个 Graph Set 行，属 D18 系统性缺口的新实例，非本轮清理遗漏 |
| 临时目录 | `/tmp/r3009-round3/`（driver/stage 脚本、evidence、state）在本记录归档后删除 |
| 服务复查 | backend :8001 `/api/health` 200、frontend :5173 200、Oxigraph :7878 200、`ontology-platform.service` active |
| 边界 | 未修改任何产品代码；未触碰 `docs/requirements/requirements-v3.0.md`、011 两份文档、`AGENTS.md`/`CLAUDE.md`、`.codex/agents/`；未 git commit；未启动真实 `semantic modeling start`；R2.3 旧任务未被触发 |

### 10.9 本轮结论

**PASS（含 3 项 Low 缺陷与 1 项遗留清理缺口）**。Round 2 全部缺陷（D2/D13/D14/F08/D15）经真实入口 + 真实存储独立复验为 FIXED：
三类 Shape 目标可创建/可读/可校验（S17）、多 Shape 冲突显式 409（F08）、apply 失败不再锁死 Ontology 且真实数据违例仍被拒（D13/F16）、
缺图读返回 200 + `missing_graph_iris`（D14）、同批 create→update 按声明顺序合法（D15/D11）；受本轮改动影响的回归（S08、S03、D12、B01、B03/D7、B10、
R13/R03、S15/S16、D9/D10 存储级孤儿检查）全部维持 PASS。四套自动化独立复跑：backend **1006 passed**、playwright **39 passed**、build 成功、
validate exit 0、009 专用用例 backend 29 + modeling_team 24 全绿；modeling_team 的 7 个失败已证明为与本需求无关的环境性失败。

不阻塞验收的遗留项：
1. **D16（Low）**：`shape_conflict` message 重复前缀且只报 graph IRI，不报冲突的 shape IRI（可诊断性）；
2. **D17（Low）**：`_ordered_shape_refinement` docstring 与实现不一致（反向声明顺序也被豁免）；
3. **D18（Low，遗留）**：项目/Ontology 删除不级联清理 Graph Set 与 named graph，本轮夹具又产生 2 条孤儿 Graph Set + 4 个孤儿 graph（建议随下一批补生命周期接口或级联删除，并同步清理本轮孤儿）；
4. Q01-Q07 与依赖真实 Team run 的用例仍未执行（R3.0-006 授权未开放），R3.0-009 的**真实语义验收**（§5）整体仍未开始。

建议：R3.0-009 平台/流程增量可通过本轮；3 项 Low 可与后续批次合并处理，不要求先修再测。真实语义验收（Q01-Q07）在 006 授权开放后另行安排轮次。
