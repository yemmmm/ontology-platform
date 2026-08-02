# v2.4 通用 RDF Literal 建模能力需求

## 文档信息

- 文档状态：R2.4-001 已记录、待独立细化；不作为 R2.3-002 完成前置
- 基础版本：`docs/requirements/requirements-v2.3.md`
- 关联版本：`docs/requirements/requirements-v1.0.md`、
  `docs/requirements/requirements-v2.1.md`、`docs/requirements/requirements-v2.2.md`
- 当前待细化需求：R2.4-001 通用 Modeling Batch 显式 RDF Literal Envelope
- 总体目标：让业务无关的 Modeling Batch 能显式、无歧义地写入和读回 RDF plain、typed 与
  language-tagged literals，同时保持 Evidence、lineage 和 fact identity 完整
- 更新日期：2026-08-02

## 背景

R2.3-002 P2a 已把当前最小 live scope 收窄为实际 plain literal 写入和
plain/full-XSD-string proof comparison，不要求显式 datatype 或 language-tagged literal 的真实写入。
当前 Modeling Batch 的 entity properties 主要接受普通 JSON scalar；compiler 可从部分 JSON primitive
推导 boolean/integer/decimal term，但调用方没有一个通用、显式且可 round-trip 的 RDF literal envelope
来区分 lexical value、datatype IRI 和 language tag。

这个缺口是平台通用 RDF 建模能力，不是 P2a、Dify Workflow 或某一业务 ontology 的特殊需求。
它不得在 R2.3-002 的四 item fixture 中通过领域字段、专用 command、硬编码 predicate 或测试解释逻辑
绕过。v2.4 单独记录该能力，后续经过需求细化、设计 review、实现和真实验收后再声明支持。

## 与既有版本的关系

1. v2.4 继承 v1.0 的 Semantic Platform Core、Modeling Batch、Evidence、lineage、权限和持久化边界，
   不把 Agent label 或推断的 datatype/language 当作平台事实。
2. v2.4 以 v2.3 的 formal receipt、normalized delta、fact ID、statement read、Evidence association 和
   governed retrieval 合同作为 round-trip 证据，不改变 Team Runner 或三 Agent 角色语义。
3. R2.4-001 不是 R2.3-002 P2a、唯一剩余 semantic start、fresh `t` 或 R2.3-003 的完成前置；任何
   实现只能在 R2.4-001 独立细化并授权后开始。
4. 该能力必须对任意 ontology/predicate 可用。Dify、Workflow、Output、publicationStatus 等参考名称
   只能出现在 fixture/assertion 中，不能进入 production API、handler、compiler 或 read model 分支。

## 需求列表

| ID | 需求 | 优先级 | 当前状态 | 主要依赖 |
| --- | --- | --- | --- | --- |
| R2.4-001 | 通用 Modeling Batch 显式 RDF Literal Envelope | P1 | `待细化` | R2.3 formal Modeling Batch/Evidence/lineage/readback 合同 |

## R2.4-001 通用 Modeling Batch 显式 RDF Literal Envelope

当前状态：`待细化`

优先级：`P1`

### 现状是什么，需要改成什么

当前：

- Modeling Batch 调用方不能用一个稳定、显式的 payload 同时表达 lexical value、datatype IRI 或
  language tag；
- 普通 JSON scalar 到 RDF term 的 compiler 推导不等于调用方显式声明，无法完整表达 language tag；
- typed/language literal 的 handler/API 拒绝规则、normalized delta、readback 和 lineage round-trip
  尚未形成同一个验收合同；
- R2.3 proof static branches 能验证 term comparison，但不能证明真实 write/read 支持。

目标：

- 为通用 Modeling Batch literal value 增加显式 RDF literal envelope；
- handler、compiler 和 API/MCP schema 对同一 envelope 做一致、确定性的验证和编译；
- formal receipt、normalized delta、RDF storage、statement/entity read、fact ID、Evidence/lineage 和
  governed retrieval 保留同一实际 lexical/datatype/language term；
- 通过业务无关的真实 Batch acceptance 分别证明 plain、typed 和 language-tagged round-trip。

### 待细化的最小功能合同

1. Envelope 至少表达 `value, datatype, language`。`value` 是实际 RDF lexical value；`datatype` 为
   absolute datatype IRI 或 null；`language` 为合法 language tag 或 null。`datatype` 与 `language`
   互斥，二者不得同时非 null；二者均为 null 表示 plain literal。
2. Envelope 使用精确可辨识的 object shape，拒绝 unknown fields、缺失 value、非法 datatype IRI、
   非法 language tag、datatype+language 同时存在、非 literal target 和与 Item reference 冲突的形状。
   legacy scalar 是否保持兼容及 envelope 可出现的具体 command fields 在需求细化时冻结。
3. Handler validation、API/MCP validation 和 compiler 必须采用同一合同。compiler 正确 escape lexical
   value，并分别生成 plain、`"lex"^^<datatype-iri>` 或 `"lex"@language`；不得按 label 猜 datatype，
   不得把 plain 静默重写为显式 `xsd:string`，也不得丢弃原始 lexical form。
4. 对已知 XSD datatype 的 lexical validation、language tag canonicalization、unknown absolute
   datatype IRI 的允许范围、空 lexical value 和 legacy compatibility，必须在 R2.4-001 细化阶段明确，
   不能由实现自行选择。
5. Dry-run operation plan 和 apply receipt 必须以 source-minimal 方式证明实际编译 term；
   normalized applied delta、stored RDF quad、fact ID、statement/entity read 与 generic semantic query
   必须 round-trip 同一 lexical value、datatype/language，不接受仅以 candidate 或请求 echo 证明。
6. Existing inline Evidence、Modeling item origin、statement occurrence、EvidenceReference association
   和 resource/statement lineage 必须继续绑定到该实际 literal fact；typed/language 支持不得绕过
   `missing_evidence`、authorization、lease、workspace 或 atomic/recovery 合同。
7. API/MCP、service、compiler、repository/read model 和 export/import 受影响面必须在设计前完成 impact
   analysis；不得增加业务专属 route、schema、field、command kind、sorting rule 或 query interpretation。

### 初始 live acceptance

后续细化至少应包含一个 disposable、业务无关的真实 Modeling Batch acceptance，并独立读取正式
receipt/delta/storage/read/lineage 证据，覆盖：

1. plain literal round-trip，实际 term 无 datatype/language；
2. 显式 full-IRI `xsd:string` round-trip，且不与 plain stored term 混报；
3. `xsd:boolean`、`xsd:integer`、`xsd:decimal` 的代表 lexical value 与错误 lexical value；
4. 一个 language-tagged literal 及 datatype+language、非法 tag 负例；
5. update/idempotent replay/conflict、Evidence/lineage、fact ID 和 generic retrieval round-trip；
6. legacy scalar compatibility、unknown field/shape、unsupported target 和跨接口 validation 一致性；
7. 不含任何 Dify/P2a/Workflow production branch，且不会改变 R2.3 已接受的 plain-only P2a 结论。

### 非目标

- 不为 R2.3-002 补做或重判 P2a PASS，也不恢复已取消的 P2a live typed/language gate；
- 不新增领域专属 literal command、predicate、datatype alias、read model 或自然语言解释；
- 不在需求细化前决定 migration、storage rewrite、legacy backfill、UI editor 或 generalized versioning；
- 不用 static verifier success、request echo 或 mock-only compiler test替代真实 write/read/lineage evidence。
