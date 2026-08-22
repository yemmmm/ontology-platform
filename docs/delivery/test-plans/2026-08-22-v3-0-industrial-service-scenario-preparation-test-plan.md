# v3.0 工业售后服务场景准备与数据基线 — 共享测试计划

- 日期：2026-08-22
- 状态：PASS（mandatory plan review、开发 D1、独立 Round 1 均完成）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-001
- 设计：
  `docs/delivery/designs/2026-08-22-v3-0-industrial-service-scenario-preparation-design.md`
- 被测数据库 schema：`industrial_service_v3`
- 执行者：开发者先自测；`requirement_tester` 在稳定状态独立复核并把轮次追加到本文

## 1. 测试边界

本计划只验收 R3.0-001。它不创建 Ontology/RDF 业务实例，不启动 Modeling Agent，不调用 Consumer
Agent，不证明 `forbidden` 已实现，也不把直接 SQL 查询成功解释为安全验收。

所有破坏性数据库操作只能由安全 loader 命中精确 schema `industrial_service_v3`。loader 必须先以
只读 SQL 确认当前数据库、目标 schema owner/comment marker 和非目标 relation sentinel；不允许对
`public`、平台表或其他 schema 执行 DROP/DELETE/TRUNCATE。现有同名但 marker 不匹配的 schema
必须 fail closed。

## 2. 稳定测试命令

以下命令从仓库根执行。容器用户名和数据库名从容器既有环境读取，不在日志中输出密码：

```bash
docker compose config --services
./scripts/load-industrial-service-v3-postgres.sh
```

loader 是唯一支持的装载入口；它必须输出目标数据库、目标 marker、装载前/后的非目标 relation
sentinel 和装载结果，但不得输出密码。查询验证使用提交的 `verification/verify.sql` 和
`expected-results.json`；测试者可增加临时只读反例，轮次结束后删除，不提交第二份 Schema/seed。

## 3. 轮次与用例

### T1 文档和信息边界

1. 需求、设计、场景 README、delivery reference 业务流程、输入 manifest、场景简介、业务术语、
   Schema、样例、verification 合同和安全 loader 全部存在，内部链接可解析。
2. `input-manifest.json` 是合法 JSON，只列出 `modeling-input/` 内的四个实际输入文件，不包含或引用
   delivery reference、`verification/`、共享测试计划、查询答案或预期 Case 标签；场景输入树外的
   业务真值不被任何 input 文件链接或复制。本轮只证明资料分类边界，运行时文件访问负例留到
   R3.0-006，不宣称已有 OS sandbox。
3. 建模输入中的业务术语保持简短，显式列出需要用户澄清的未知项；不直接给出完整 SLA/重复故障/
   一次修复/延迟归因口径。
4. `docs/delivery/reference/industrial-service-v3-business-process-reference.md` 明确标记“不得作为建模
   输入”，并包含切片关系、主流程、异常分支、指标口径、权限示例和 competency questions。
5. 全仓新增场景文件不含密码、真实连接串、API key 或个人信息。

### T2 SQL 静态结构

1. `schema.sql` 的删除目标只能是精确 `industrial_service_v3`；已存在 schema 的 owner/comment guard
   在 DROP 前执行；创建后设置固定 marker 和受控 `search_path`。不包含 `public` 或其他 schema 的
   DDL/DML。
2. `schema-contract.json` 是合法 JSON，SHA-256 匹配 `schema.sql`，并冻结设计列出的 21 张表的所有
   列、顺序、类型、NULL/default、PK/UNIQUE/FK/CHECK 和必要索引；实际目录结构 exact match。
3. 关键枚举/范围/时间约束存在：severity、work order status、delay cause、movement/request/shipment
   status；正数量、非负成本、合法时间顺序。
4. `sample-data.sql` 自行设置目标 `search_path`，不创建表、不关闭约束、不使用随机值/当前时间/未限定
   外部对象；所有时间带明确时区，所有 ID 显式稳定。两个 SQL 分别执行时，DML 也只解析到目标
   schema。
5. loader 只接受固定文件/目标，失败关闭，并对非目标 relation sentinel 做前后比较；SQL 中没有
   RDF、Ontology 或平台产品表写入。

### T3 PostgreSQL 装载与可重复性

1. Compose 含运行中的 `postgres` 服务，连接和 `select 1` 成功。
2. 首次执行安全 loader 成功，无未处理 SQL 错误；输出中的非目标 relation sentinel 前后相同。
3. 查询 `pg_tables` 得到 `industrial_service_v3` 下恰好 21 张预期表。
4. 记录每表行数；所有表非空，核心基数满足：3 regions、3 customers、5 sites、4 models、10 assets、
   2 SLA policies、4 contracts，incidents/work_orders 各为 10～14。
5. 再执行安全 loader，第二次表清单、每表行数和每表 canonical 内容摘要与第一次完全一致，并与
   `expected-results.json` 完全匹配。
6. PostgreSQL 外键检查查询返回 0 个孤儿；约束负例在 transaction/savepoint 内被拒绝且回滚，不
   污染稳定数据。

### T4 关键场景 SQL 证据

独立测试者执行提交的只读 `verification/verify.sql`，将规范化结果与
`verification/expected-results.json` exact compare；可增加独立查询，但不得只按输入文档中的标签
取行。验证合同冻结 C01～C08 的确切业务 ID 和关键计算值：

1. 至少一张有效合同覆盖的 P1 工单超过解决目标，且存在重叠的
   `PART_SHORTAGE` delay、part request 和 shipment（C01）。
2. 至少另一张有效合同覆盖的 P1 工单超过解决目标，延迟原因是
   `DISPATCH_CAPACITY`，且不能被备件短缺条件选中（C02）。
3. 至少一张有备件请求/发运的工单在解决目标内完成，证明“用过备件”不等于“备件导致 SLA
   违约”（C03）。
4. 至少一张工单的 delay 原因是 `UNKNOWN`，查询不得把它归到已知原因（C04）。
5. 至少一个 incident 在发生时没有有效 `contract_assets` 覆盖，SLA join 返回 not applicable 所需的
   null/absence，而不是伪造 breach（C05）。
6. 同一资产同一 failure code 在 30 天窗口内至少出现两次（C06）。
7. 至少一个 part request 的 shipped quantity 小于 requested quantity、状态为 `PARTIAL`，关联工单
   尚未解决（C07）。
8. 至少一个无需备件且按时响应/解决的正常对照（C08）。

9. 至少一个业务可空字段实际为 SQL `NULL`，至少一个合法 empty 关系（例如某工单无 part request）
   由 `NOT EXISTS` 证明；空字符串不得冒充 NULL，所有“未知”不得被强制映射成已知枚举。

每项记录实际返回的稳定业务 ID 和关键计算值，不能只记“命令退出 0”。

### T5 全局原则、术语和范围守恒

1. 根 `AGENTS.md` 记录可跨场景复用的关系型语义层指导：RDF 不存业务行、Schema 非业务真理、
   完整场景切片但不预判 Ontology 拓扑、先授权语义后 SQL、语义权限与数据权限分离。
2. `docs/reference/glossary.md` 定义 Business Scenario、Logical Modeling Slice、Semantic Mapping、
   Semantic Knowledge Authorization、Business Data Authorization、SQL Execution Adapter，并避免将其与
  现有 Project/Ontology/Graph Set 混同。
3. 以 delivery baseline 为基准合并 `git diff --name-only <baseline>` 与
   `git status --short --untracked-files=all` 的完整 changed-path 清单；不含 backend/frontend/migration
   产品代码、RDF 数据、adapter/RBAC 实现或真实 modeling run 证据。不能用会漏掉 `??` 的裸
   `git diff` 判定。
4. v3.0 需求状态只允许 R3.0-001 完成；R3.0-002～R3.0-006 保持待实现/待验收。

## 4. 判定规则

- **PASS**：T1～T5 全部通过；数据库第二次装载稳定；没有信息边界泄露或越界实现。
- **FAIL**：任何文档/SQL/关系/关键 Case 不一致，或测试发现写入了非目标 schema、RDF 或产品表。
- **BLOCKED**：仅用于 PostgreSQL 服务无法运行、环境无 Docker/psql 等无法通过本轮修复的外部
  条件。现有 collation warning 若不影响 DDL/DML/查询，只记录残余风险，不判 BLOCKED。

## 5. 开发自测记录

### Round D1 — 2026-08-22 18:18 +08（requirement_developer）

- **稳定状态与边界**：未修改 backend/frontend/migration 产品代码，未创建 RDF/ Ontology/Modeling
  Batch/Agent run，也未实现 Adapter/RBAC。`git diff --check` 通过；完整 changed-path 清单保留给主
  Agent 在交付记录中汇总。共享 Compose 的 PostgreSQL 运行正常；每次 psql 输出仍有既存 collation
  version mismatch（created 2.41，OS 2.36），本轮未修改数据库级设置。
- **T1 文档/隔离**：`jq -e .` 通过 `input-manifest.json`、`schema-contract.json` 和
  `expected-results.json`；manifest 只列 `scenario-brief.md`、`business-terms.md`、`schema.sql`、
  `sample-data.sql` 四个实际文件。输入树未引用业务真值、verification 或测试答案，完整业务真值
  单独位于 `docs/delivery/reference/` 并明确标注不得作为建模输入；输入术语保持简短并列出待访谈项。
- **T2 SQL/schema**：`bash -n scripts/load-industrial-service-v3-postgres.sh` 通过；schema 与 seed
  均显式 `SET search_path TO industrial_service_v3, pg_catalog`，DDL 只有精确目标 schema。契约中的
  `schema_sql_sha256` 为
  `a75871136f50b1fc2da3a2b57a319cdfa413b88f0b8bb82edb2e31175f342fac`；catalog projection（列顺序、
  data/UDT 类型、nullable/default、PK/UNIQUE/FK/CHECK、FK update/delete action、索引定义）以
  `jq -cS` 与 `schema-contract.json` exact compare 通过，21 张表。
- **T3 装载/重装**：连续两次执行 `./scripts/load-industrial-service-v3-postgres.sh` 成功；两次
  非目标 relation sentinel 都是 `4a9b5f6fb5ae13ba9848cb5e0e2053d2`，目标表数 21，第二次
  `verify.sql` 输出与 `expected-results.json` `cmp` exit 0。稳定基数为 regions/customers/sites/models/
  assets = `3/3/5/4/10`，SLA policies/contracts = `2/4`，incidents/work_orders = `12/12`；其余表行数
  及每表 canonical digest 已冻结在 expected 文件。
- **T4 C01–C08/边界**：`verify.sql` 只读输出与 expected exact compare 通过；关键值为 C01
  `INC-1001/WO-1001` P1 response 20、resolution 600、target 240、overage 360、`PART_SHORTAGE`、
  `REQ-1001/SHIP-1001`；C02 `INC-1002/WO-1002` response 180、resolution 540、targets 30/240、
  `DISPATCH_CAPACITY`、part request count 0；C03 `INC-1003/WO-1003` response 30、resolution 420、
  target 960、request/shipment present and within target；C04 `INC-1004/WO-1004` cause `UNKNOWN`、
  resolution 900/target 960；C05 `INC-1005/WO-1005` valid coverage count 0 and SLA not applicable；C06
  `AST-006/F-OVERHEAT` `INC-1006`→`INC-1007` 13 days；C07 `REQ-1003` requested 4/shipped 2,
  `PARTIAL`/`WAITING_PARTS`, `resolved_at` NULL；C08 `INC-1009/WO-1009` response 30/resolution 240,
  standard P2 targets 240/1440, no request and one assignment. NULL/empty checks return warranty NULL 1,
  failure_code NULL 1, symptom NULL 1, unresolved `resolved_at` 2, open delay end 1, and 8 work orders with
  no part request. Foreign-key orphan query returns 0.
- **T5 principles/range**：AGENTS/glossary changes contain the cross-scenario relational semantic-layer
  principles and canonical terms; no domain table names were added to the global guidance. Delivery remains
  R3.0-001 preparation only; R3.0-002～R3.0-006 remain pending. The loader’s owner/marker guard, explicit
  target, transaction/ON_ERROR_STOP, and pre/post sentinel checks were exercised. Negative FK and negative
  non-negative-cost CHECK inserts were caught inside a PL/pgSQL exception block and left `0` rows.
- **Residual risk/cleanup**：only the pre-existing PostgreSQL collation warning remains; no cleanup outside
  `industrial_service_v3` was performed. Test artifacts were written under `/tmp` only and are not part of the
  modeling input or committed verification contract.

## 6. 独立测试轮次记录

以下轮次由 `requirement_tester` 独立执行；包含被测工作区、命令、逐项结果、实际业务 ID、缺陷与
清理情况。

### Round 1 — 2026-08-22 18:35 +08（requirement_tester）

- **总体结论：PASS。** 本轮独立执行 T1–T5；没有发现 R3.0-001 缺陷，也没有启动 Ontology、RDF
  业务行、Modeling Agent、Consumer Agent、Adapter 或 RBAC。被测工作区 HEAD 为
  `4781f0912589f22a24d1465f70bd0a1585049ee2`；交付基线按计划为
  `ed83d4e317c56d3f8b415fb017f048db681c1728`。基线到当前工作区与未跟踪文件合并后的 changed-path
  清单如下（其中旧 R2.3 测试计划是基线以来已有提交变化）：

  ```text
  AGENTS.md
  docs/delivery/designs/2026-08-22-v3-0-industrial-service-scenario-preparation-design.md
  docs/delivery/records/2026-08-22-v3-0-industrial-service-scenario-delivery-record.md
  docs/delivery/reference/industrial-service-v3-business-process-reference.md
  docs/delivery/test-plans/2026-08-19-r2-3-009-gate-relaxation-test-plan.md
  docs/delivery/test-plans/2026-08-22-v3-0-industrial-service-scenario-preparation-test-plan.md
  docs/evaluation-scenarios/industrial-service-v3/README.md
  docs/evaluation-scenarios/industrial-service-v3/modeling-input/business-terms.md
  docs/evaluation-scenarios/industrial-service-v3/modeling-input/input-manifest.json
  docs/evaluation-scenarios/industrial-service-v3/modeling-input/sample-data.sql
  docs/evaluation-scenarios/industrial-service-v3/modeling-input/scenario-brief.md
  docs/evaluation-scenarios/industrial-service-v3/modeling-input/schema.sql
  docs/evaluation-scenarios/industrial-service-v3/verification/expected-results.json
  docs/evaluation-scenarios/industrial-service-v3/verification/schema-contract.json
  docs/evaluation-scenarios/industrial-service-v3/verification/verify.sql
  docs/reference/glossary.md
  docs/requirements/requirements-v3.0.md
  scripts/load-industrial-service-v3-postgres.sh
  ```

- **T1 PASS — 文档与输入边界。** 逐项确认 13 个需求/设计/参考/场景/验证/loader 文件存在；三个
  JSON 文件以 `jq -e .` 解析成功。`input-manifest.json` 的 `allowed_files` 与
  `modeling-input/` 除 manifest 外的实际文件 exact match：`scenario-brief.md`、`business-terms.md`、
  `schema.sql`、`sample-data.sql` 四个文件。对四个输入文件扫描未发现业务流程参考文档、
  `verification/`、`schema-contract`、预期答案、CQ 或 C01–C08 标签的引用/复制；术语与摘要保留待访谈
  未知项。参考文档明确“不得作为建模输入”。场景文件和 loader 的 secret、连接串、API key、私钥、
  个人路径扫描为空。

- **T2 PASS — SQL 静态结构与目录合同。** `bash -n scripts/load-industrial-service-v3-postgres.sh`、
  `git diff --check` 通过；`schema.sql` SHA-256 为
  `a75871136f50b1fc2da3a2b57a319cdfa413b88f0b8bb82edb2e31175f342fac`，与
  `schema-contract.json.schema_sql_sha256` exact match。Schema 只 DROP/CREATE 精确
  `industrial_service_v3`，owner/comment guard 在 DROP 前，marker 为
  `ontology-platform:v3-industrial-service-fixture`；schema/seed 都显式设置
  `search_path TO industrial_service_v3, pg_catalog`，没有 public/其他 schema 或 RDF/Ontology/平台表
  DDL/DML，也没有随机值、当前时间或外部连接。独立从 `information_schema`/`pg_catalog` 投影的
  140 列、PK/UNIQUE/FK（含 update/delete action）和 60 个索引与合同 exact；21 张表共 35 条 CHECK
  通过临时表按合同表达式重新交给 PostgreSQL parser 后逐条 exact（原始 `pg_get_constraintdef` 的
  外层冗余括号与 `(0)::numeric` 只是 PostgreSQL 格式化差异）。Loader 静态固定输入路径、目标 schema、
  `ON_ERROR_STOP`、`--single-transaction` 与前后 sentinel，并在本轮运行中得到验证。

- **T3 PASS — PostgreSQL 装载、重复性与完整性。** `docker compose config --services` 返回
  `postgres`、`oxigraph`，两者 running；连接探针为 `ontology_platform / ontology / SELECT 1`。
  安全 loader 连续两次成功；两次 `non-target relation sentinel before/after` 均为
  `4a9b5f6fb5ae13ba9848cb5e0e2053d2`，目标 schema owner 为 `ontology`、marker exact，表数为 21。
  两次按主键排序的 JSONB canonical digest 与行数均与 `expected-results.json` exact；独立查询记录为：

  ```text
  assets 10/52da8996d3967ac60a83709cb0903385
  contract_assets 10/4c5080ffbda7f771ad49de55c487f624
  customers 3/929febd6c9f596419a82662f2f78c1ce
  equipment_models 4/905f844f63234682a103444208ae20a3
  incidents 12/37947b43a3a991ee45f1bb54cfa9bb63
  inventory_movements 12/1536a399bddd82f44ee4fc71b1058c9f
  part_compatibilities 8/d745b3a804ffbfc050c6c72f39515625
  part_requests 4/1d1fca8e518f96ebeaefcb4136c98ad1
  part_shipments 4/aa19fe764b28033072e9da23435ed37e
  service_contracts 4/f18995386d78fec1a63929c238abbdba
  service_regions 3/2925eb7b6c20eaf1cc347f85b6179d8a
  service_sites 5/b4842ab9a3ef662bb2ba29b66ea64305
  sla_policies 2/cb7c508a9f5fce87ee6786394b87e372
  sla_targets 8/dfda8b7fcec8944887ed2ccce55bda52
  spare_parts 6/f0e2713c4780896a2f204a7a486eb421
  technicians 5/6a46921b6d808463dd75e69547f81a77
  warehouses 3/57666558b762fd3710baaf6ee98101ca
  work_order_assignments 11/40ad9b826290a5ec8b8a13d1c090eca1
  work_order_delay_events 6/5b9cc06d6bda3b00dd380c77e9286975
  work_order_status_events 35/94b186a2ef915d08fb65618d8c763839
  work_orders 12/939ece0d0885c9a3b18e3342e2f0b500
  ```

- **T4 PASS — 只读验证、C01–C08、NULL/empty、负例。** 提交的 `verification/verify.sql` 输出在去除
  psql 的两行 `SET` 回显后与 `expected-results.json` exact；独立重写查询再次核对以下稳定业务 ID
  与关键值：

  ```text
  C01 INC-1001/WO-1001/AST-001: response 20, resolution 600, target 240, overage 360,
      PART_SHORTAGE, REQ-1001/SHIP-1001
  C02 INC-1002/WO-1002: response 180, resolution 540, targets 30/240, overages 150/300,
      DISPATCH_CAPACITY, part_request_count 0
  C03 INC-1003/WO-1003: response 30, resolution 420, target 960, within_target true,
      REQ-1002/SHIP-1002 SHIPPED
  C04 INC-1004/WO-1004: UNKNOWN, resolution 900, target 960
  C05 INC-1005/WO-1005/AST-009: valid_coverage_count 0, target_count 0, sla_applicable false,
      resolution 150
  C06 AST-006/F-OVERHEAT: INC-1006 -> INC-1007, 13 days
  C07 INC-1008/WO-1008: REQ-1003 requested 4/shipped 2, PARTIAL/WAITING_PARTS, resolved_at NULL
  C08 INC-1009/WO-1009: response 30, resolution 240, targets 240/1440, no requests, assignment_count 1
  ```

  独立 nullable 投影确认 `warranty_end_date` NULL 1、`failure_code` NULL 1、`symptom` NULL 1、
  `responded_at` NULL 1、`resolved_at` NULL 2、`delay_end_at` NULL 1，所有 nullable text 列空字符串数
  均为 0。`NOT EXISTS` empty 关系精确返回 8 个工单：`WO-1002`、`WO-1004`、`WO-1005`、`WO-1006`、
  `WO-1007`、`WO-1009`、`WO-1010`、`WO-1012`。独立 26 个 FK orphan 查询全为 0；FK 负例、负成本
  CHECK 和时间顺序 CHECK 均在 transaction/savepoint 内被拒绝，回滚后 sentinel 行数均为 0。

- **T5 PASS — 全局原则与范围守恒。** AGENTS.md 的关系型指导覆盖 RDF 不存业务行、Schema 只是映射
  证据、完整场景切片但不预判 Ontology 拓扑、先授权语义后 SQL、语义知识权限与业务数据权限分离及
  最小 SQL executor；glossary 定义六个要求的跨场景术语且未混同 Project/Ontology/Graph Set。合并
  `git diff --name-only <baseline>` 与 `git status --short --untracked-files=all` 的完整清单不含
  backend/frontend/migration 产品代码、RDF 数据、Adapter/RBAC 实现或真实 Agent run；需求状态保持
  R3.0-001 本轮交付中、R3.0-002～R3.0-005 待实现、R3.0-006 待验收。

- **实际命令与残余风险。** 除上述 loader、verify、catalog/目录投影和独立只读 SQL 外，执行了
  `docker compose config --services`、`docker compose ps --status running --services`、`jq -e .`、
  `sha256sum`、`bash -n`、`git diff --check`、T1 secret/path scan。所有临时输出均写入 `/tmp/v3-*`，
  测试结束已删除，不进入 modeling input 或提交内容。每次 psql/loader 仍输出环境既存
  `database "ontology_platform" has a collation version mismatch`（created 2.41，OS 2.36）；DDL、DML、
  验证和重复性未受影响，本轮不修改数据库级设置，不判 BLOCKED。没有缺陷需要回到开发修复或开启下一轮。
