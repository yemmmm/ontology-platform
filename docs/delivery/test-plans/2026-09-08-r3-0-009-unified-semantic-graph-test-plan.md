# R3.0-009 统一语义图与共性抽象：共享测试计划

状态：独立计划评审 Round 3 PASS（2026-09-08），无遗留 Critical/High；以下功能测试均**尚未执行**。

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
- `shape0/shape1`：无类节点 Shape、两个 Class 的可合并 Shape 和一个显式冲突；
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
| 评审状态 | Round 1 REVISE；Round 2 确认 H1/H3 与 H2 字段绑定部分闭合，保留批准快照 High；Round 3 PASS，无遗留 Critical/High |
| 发现/处置 | H1/H2/H3 均 accepted-high；审批schema兼容、投影绑定及Task选择路径分别按设计§9.1/9.2/3.2补齐 |
| 测试调整 | 增加S13/S14、F11/F12/F13、R11，覆盖模式分派、完整内容篡改、定向写权限、新旧回放与未知结果对账 |
| Round 2处置 | 批准后固定版本与接收时点已写入设计§9.2；F14验证接收前拒绝、接收后快照不被源路径变更替换及现有工作区版本冲突 |
| Round 3复核 | 独立 plan_reviewer 确认剩余 High 闭合；权威需求、设计§9.2与F14一致，无待确认项。仅计划评审通过，不代表本计划功能/语义测试通过 |
| 文档检查 | 2026-09-08：三份文档的本地链接/路径引用、代码围栏、D1-D9 对应和 56 项用例编号检查通过；34 个现有引用可解析，2 个明确标为待实现的任务/合同资产未创建；git diff --check 通过。只证明文档完整性 |

本计划所有测试状态当前为 `NOT_EXECUTED`；实现阶段若发现源码合同与本计划冲突，应先记录证据并回修设计，
不能以降低测试范围代替解决需求冲突。
