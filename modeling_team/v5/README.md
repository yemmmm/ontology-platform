# OntoWeave v5 执行入口

归属：[R5.0-001](../../docs/requirements/requirements-v5.0.md#r5-0-001)、
[R5.0-012](../../docs/requirements/requirements-v5.0.md#r5-0-012)、
[实施计划 P0](../../docs/delivery/implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#5-p0在全面改造前验证什么)。

新任务默认入口为 `scripts/modeling`：LangGraph＋Codex harness、动态递归工作树、直接 HITL、
通信／卡片／固定版本材料、项目记忆、持续语义工作空间、增量修模、实际应用与治理读回、
模型版本总览、数据快照分叉，以及独立全范围／有界评价。prepare 自动冻结当前方法和
平台技术合同，Task instructions 只需任务补充。最新验证及限制见
[持续推进记录](../../docs/delivery/records/2026-10-29-v5-autonomous-progression.md)，
公开工程用例不代表完整业务盲测或净降耗证明。

## 新任务默认专职团队

正常 `start` 未填团队选择时冻结 `team_contract: role-team/v1`。程序建立 Coordinator、
公共 CQ 专职和 Modeler；单槽先运行真实来源 intake，再按 Coordinator 的确切范围版本
接续正式建模，多槽可并行。小任务也保留专业职责，已有题由 CQ 复核复用。
默认不依赖根 Agent 自愿 delegate，不把过程评分当生产 CQ。

Profile 必须逐项配置 `coordinator`、`competency-question`、`modeling`、`acceptance`；
可以用同一模型，各自保留独立身份、上下文、提示、工具和实际用量。prepare 冻结专业包与
工具列表及摘要，缺配置在创建 run 前给可修正错误，不沿用 modeling 冒充其他角色。
新模式用 semantic workspace 保存带作者的判断；`shared_memory` 旧工具不挂给新团队。

Coordinator 提交 `scope-plan/v1`，Modeler 提交可执行候选／显式变更，CQ 提交
`public-cq-set/v1`。生产 CQ 不读私有题、答案或评分；draft 不自动变成确认事实。
Coordinator 的 `integration-plan/v1` 只选择固定版本原贡献，程序限定 item/change ID、
保留业务字段和作者，再由 Host 单写应用。中间 Coordinator 用 `coordination_refs`
交接原计划，保留叶作者，并按原树安排叶子／中间父级／根的实际读回。
同资源冲突返回责任方；不猜原生身份，不按名称合并，不恢复 Protocol 翻译或模型 dry-run。

`status`／`work-tree`／`board` 披露团队、role、actor、工作类型、代次／范围与在途活动。
消息、已读、完整消费、依赖满足、实际应用、生产检查及独立接受分别保留。
未知执行／写入先沿原身份对账，不能通过新代次、计划或新会话重放。暂停／预算控制覆盖
所有在途角色，停稳后再收尾；临时读取能力统一清理。
Host 保留真实授权收取时间（`authorization.received_at`）；`semantic-starts/` 保存真实
原生 turn/started 的角色／作者／用途／线程及时点，业务开始还须核对实际来源分析和读取，
不能用创建线程或空调用证明。时间缺失保持未知，不拿 prepare 时间重置授权时钟。

无此合同的既有 binding 沿旧路径接续，不迁移旧原生上下文。新任务只有显式选择
`single-modeler/v1` 才用单根模式，状态会披露；不因配置错误自动降级。
快照 fork 保留源团队合同、创建新原生上下文；专职团队重新登记当前工作，不复制旧树或
继承旧检查／验收。工程证据与真实采用边界见
[R5.0-012 交付记录](../../docs/delivery/test-docs/2026-11-03-r5-0-012-delivery.md)。

### 交付与技术纠错合同

2026-11-04的[流程修订](../../docs/delivery/designs/2026-11-04-role-team-flow-repair-design.md)
明确以下兼容增量；工程证据见[验证记录](../../docs/delivery/test-docs/2026-11-04-role-team-flow-repair.md)。

- `role-work-result/v1`可选`artifact_ref`只接受prompt给出的`retained_artifact_ref`，且
  `artifact=null`；本作者同基线的纯信封纠错可避免重交正文，任意/陈旧引用仍拒绝。
- prompt的`reusable_read_execution_refs`是程序验证的同作者、阶段、generation、来源/
  scope/CQ/shared/model及业务答复基线上的真实读证明。未列出的历史、未读/缺页材料
  不能声称已消费。新业务答复使旧成果复用失效；有原生绑定时沿已有resume并差分计量。
- 候选仅缺`relation_endpoints`/`shared_scope`时可补null，原字段值及业务正文不变；
  单一已授权Ontology用`ontology_targets={}`复用已有投影，多目标仍须明确放置。
- `public-cq-set/v1`可选`model_support=[{cq_id,status,evidence}]`记录实际支撑，status为
  supported/conditional/unsupported/unverified。仅该证据变化进入原属主self_check；
  questions/unknowns/coverage_gaps的真实变化仍交原责任重评，不把证据槽当业务事实来源。
- 卡片/record/source工具schema显式体现既有字段；reported_at由程序盖章，已绑定源的
  semantic record可省略SHA。身份、摘要、引用和授权错误继续准确反馈。

新任务会冻结更新后的专业提示；旧run保留原冻结材料/提示，只兼容程序增量，不能宣称已
热替换所有旧指令。新CLI加载修复也不会恢复已关闭预算或自动开始调用。

### 精确模型读取与当前后续验证

生产、自查和独立评价在 `read_material`／`query_semantic_context` 外，可使用只读工具
`read_model_resource(ontology_id, family, resource_iri=None)`。`family` 为 `class-detail`、
`property-list`、`relation-type-list`、`entity-detail`、`table-mapping-detail` 或
`join-mapping-detail`；它沿既有受治理 read-model
接口展开真实 IRI，保留 Host 绑定的本体范围、只读凭据和冻结 revision 检查。
先召回定位、再按需精确展开；召回无命中不证明模型不存在相应事实。

`operation-detail` 同样按真实 IRI 精确读取。读取整个 `resource-list` 时省略
`resource_iri`；提供 IRI 会过滤清单。`resource-relations` 返回整个获准本体关系图，
不按 IRI 过滤。结果中的 `read_scope` 标明请求范围，`paging.complete` 只针对该范围；
单个资源过滤后的 complete 不证明全本体完整。查询截断／退化时优先展开已知 IRI。

新 Task 冻结的方法合同包含完整 Class／relation_type 请求示例，
以及 table_mapping／join_mapping 的完整载荷、列／连接步骤和按类型限定的 mapping_definition
结构；类型名选择结构，不作为 mapping_definition 的外层键。
候选引用字段按 definition_ref／existing_resource_ref 对象描述，compiled_format 单列后端
IRI 类型；完整中立候选示例包含全部必填字段和 item_id 选择，避免把 API 输出形状当候选输入。
格式反馈沿原目标可修正。工作空间用现有 states 和精确 depends_on 维护业务状态及依赖，
不新增语义必填硬门。
工作空间导航显示已有 states／model_basis；根级与原单元自查附上本单元的 task／project
记录导航。它包含分配给本单元及本单元署名的记录；分页使用相同 scope、unit_id、
`include_authored=true` 和 next_offset。普通按单元搜索默认仍只匹配 unit_id。
这些信息不自动完成记录；Agent 须根据实际读回更新原记录或明确取代旧记录。
后续任务、验收正反例、原始失败和未验证范围见
[统一计划](../../docs/delivery/implementation-plans/2026-10-30-v5-next-tasks.md)及
[逐轮记录](../../docs/delivery/test-docs/2026-10-30-v5-follow-up-validation.md)。

父级可在建模提案的可选 `review_units` 中声明需要实际读回的已就绪直接子级；
程序在应用／no_change 后、父级整体自查前调用原责任单元。中间提案可声明其直接子级，
递归检查先于本层；原自查结果的 `review_units` 路径保留。
程序沿原工作单元、候选／来源／代次和模型版本绑定独立的生产上下文；子级负责自己的
语义检查，Host 仍统一执行模型应用。相同基线的已完成检查复用原证明，模型变化后重新检查。
局部需要修订时重开原单元及祖先，原失败保留；父级仍负责整体规则，不以子级通过数量代替。
检查结果与原始治理读取均以精确版本材料交接；父级可从证明中的
`governed_read_material_ref` 按范围下钻，不必把完整读取上下文复制进摘要。
孙级材料尚未显式交接时，先请作者或已有接收者转发确切引用；工作树可见引用不等于读取授权。
Host 也可显式调用 `scripts/modeling check-unit --run-dir ... --unit-id ...`；该操作只做
生产读回并登记结果／必要重开，不直接修改 RDF，也不是独立验收。

独立包 `ontoweave_modeling` 不导入旧
`modeling_team`／Runner，独立依赖环境不修改后端或旧任务入口。
Host-only 探针暂时复用旧工具模块，不代表 P1 生产依赖切分已经完成。
P0 的 47 项开发测试、独立工程 PASS、冻结平台小目标 6/6，以及计量 PARTIAL 边界见
[验证记录](../../docs/delivery/test-docs/2026-10-28-v5-codex-p0-validation.md)。
旧 `python -m modeling_team` 保留，`scripts/modeling --legacy ...` 继续历史任务；旧 checkpoint
不交给 v5，已有 v5 run 也不因默认入口回退转交旧 Runner。

## 复跑

在仓库根目录执行，需要 Linux、bubblewrap 和 Python 3.12：

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/workspaces/v5-codex-p0/.venv"
uv sync --locked --project modeling_team/v5 --group dev
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling.preflight \
  --model-profile modeling_team/model-profiles/glm-flash-low.yaml \
  --role modeling \
  --output-dir workspaces/v5-codex-p0/manual-001
uv run --locked --project modeling_team/v5 pytest \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests
uv run --locked --project modeling_team/v5 ruff check modeling_team/v5/src modeling_team/v5/tests modeling_team/v5/scripts
uv run --locked --project modeling_team/v5 ruff format --check modeling_team/v5/src modeling_team/v5/tests modeling_team/v5/scripts
```

每次指定不存在的输出目录；已有目录会被拒绝，避免覆盖证据。
显式 `resume` 探针使用原目录恢复，保留原分批、业务版本、checkpoint 和 native thread。
PostgreSQL 测试通过 `ONTOWEAVE_TEST_POSTGRES_CONFIG` 指定 Host 连接文件，未配置时明确 skip；
本批真实数据库测试无跳过，仅创建并删除自有随机 schema。
`.python-version` 固定本轮 Python 系列，`uv.lock` 固定 SDK、其绑定 CLI 及依赖。
当前候选为 `openai-codex==0.163.0`／CLI `0.163.0`，与全局 CLI `0.165.0`
分开。官方 SDK 的运行时绑定说明见[官方文档](https://learn.chatgpt.com/docs/codex-sdk)。

## 检查范围

- 从指定角色的现有模型 Profile 读取 provider／model／effort，不静默回退。
- 用真实 SDK 启动其绑定的 CLI，读取生效配置，创建不含 turn 的临时 thread，
  读取原生能力开关、Skills 和 MCP 清单；保存版本、二进制与配置哈希及 RPC 返回。
- 子进程采用现有运行时的 Linux namespace 隔离方式，并额外关闭网络。
  不挂载宿主仓库、宿主 home、隐藏材料或凭据，不继承宿主环境变量；
  模型地址固定为隔离 namespace 内不可用的地址，入口不调用 `turn/start`。
- 使用逐能力原生工具配置，不沿用无效的顶层 `default_tools_enabled`。
  配置读回不证明真实出站工具集合正确，仍须后续 V2 实测。

`preflight.json` 是候选环境证据，不是模型调用、预算结算、恢复或语义验收报告。
它不创建预算、迁移数据库、恢复旧任务或写入业务模型。

## 真实集成入口与剩余边界

`preflight` 入口仍禁用网络。以下脚本使用真实模型或真实平台，必须沿当次授权、
Host 私有连接文件及自有资源运行；本批原目录用于只读证据，不能盲目重放。

| 入口 | 用途 |
| --- | --- |
| `scripts/live_probe.py` | V1 自然工具回合；默认程序校验 JSON，`--native-output-schema` 仅为旧失败对照。 |
| `scripts/integration_cases.py` | 输入隔离、可恢复 SSE 错误、真实压缩与补读。 |
| `scripts/parallel_case.py initial/resume` | 两真实 Agent 的业务记录交接及 PostgreSQL／原 native thread 接续。 |
| `scripts/control_case.py` | 两成员忙碌时排队、自然暂停／停止和输入消费。预算只注入控制信号。 |
| `scripts/draft_case.py` | Agent 从公开来源生成通用定义计划。 |
| `scripts/platform_case.py` | 使用已有 backend 环境复用编译、应用、读取和资源收尾；凭据留在 Host。 |
| `scripts/platform_graph_case.py initial/resume` | 实际应用后的 checkpoint 丢失、未知响应、确认未写入及跨批部分成功。 |
| `scripts/acceptance_case.py` | 独立只读评价冻结目标；实际材料读取、完整题集及模型修订均须核对。 |
| `scripts/memory_case.py write/consume/evaluate` | 两 Agent 同记录版本冲突合并；新消费者仅从共享记忆答题，独立侧按原始依据评价。 |

真实 Agent 已在 thread 创建前通过公开配置关闭上述系统 Skills，工具循环已实际走通。
`outputSchema` 的失败证据保留，用户已确认“自然 JSON 返回＋程序结构校验”。本任务最新授权
取消原 3 元额度门，后续 Host 探针按 `usage_only` 保留原始用量与身份；完整统计覆盖仍 PARTIAL。
此项仅适用于本任务，不改变其他任务的预算。没有新增费用总账或备用执行器。

工作空间只保存候选业务内容；checkpoint 保存执行引用，平台保有实际模型，独立报告保有验收结论。

新 Task 的 prepare 会将现有 ontology-modeling Skill 中的业务输入、场景设计及多视角／共享
变更章节直接冻结到指令，并复用 R4.0-012 的动作、流程绑定、业务规则与接口映射语义合同。
v5 根工作单元承担整合职责，使用现有语义记录维护视角适用性和实际表达引用；不使用旧工具
路由或固定七个 Agent／输出。环境 Skill 隔离保持，旧 binding／checkpoint 不自动更新。
精确治理展开还支持后端既有 `operation-detail`。章节和工具检查只是工程证据，真实方法
采用及语义完整性须通过实际模型和独立消费验证。
共享记忆有界验证与边界见[专门记录](../../docs/delivery/test-docs/2026-10-28-v5-shared-memory-validation.md)，
未据此声明完整记忆方案或净降耗通过。
跨批部分成功的恢复只复用原回执并保留已拒绝项，不自动更改分批或冒称全部完成。
P0 的原型边界按原证据保留；当前生产接线见后文及最新交付记录。完整供应商结算仍为 PARTIAL。

## P1.1 框架入口

从仓库根目录使用同一锁定 v5 环境：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 python -m ontoweave_modeling --help
```

`start`、`status`、`pause`、`stop`、`resume`、`evaluate`、`cleanup` 均显式绑定 `--run-dir`。
首次准备可使用以下命令；它只冻结输入并保存 PostgreSQL 记录，不启动模型或平台资源：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 python -m ontoweave_modeling start \
  --task /absolute/path/task.yaml \
  --postgres-config /absolute/path/postgres-private.json \
  --run-dir workspaces/v5-runs/unique-run --prepare-only
```

去掉 `--prepare-only`，或对已准备目录执行 `resume`，会按获准任务真正调用模型／平台；
首批框架验证没有执行这类真实调用，后续真实结果见上述推进记录。
日常新任务可将同样参数交给 `scripts/modeling`，无需手写 uv 环境命令。
PostgreSQL 业务 schema 默认 `ontoweave_v5_workspace`，checkpoint 默认
`ontoweave_v5_checkpoints`，可由 Host 显式指定独立名称。私有连接文件为 psycopg 连接参数 JSON，
不会挂给生产 Agent。

任务文件的完整最小形状如下。路径相对任务文件解析；所有示例占位值都须替换为真实获准内容，
其中冻结题集应在生产前由独立侧准备，`sha256` 是其原始字节摘要：

```yaml
schema_version: ontoweave-task/v1
team_contract: role-team/v1  # 省略时的新任务默认值
task_ref: authorized-task
run_id: unique-run
work_unit_id: bounded-unit
objective: 本次有界业务目标
materials: /absolute/path/approved-materials
model_profile: /absolute/path/glm-flash-low.yaml
instructions: 本次业务目标的补充；专业合同由 prepare 冻结
semantic_workspace: true
work_management: true
unit_concurrency: 2  # 可以为1，仍分别执行专业职责
authorization:
  mode: amount
  reference: 当次真实Host授权引用
  budget_ref: Host依据真实授权创建的稳定预算路径
  received_at: 实际授权收取的UTC时间（替换为ISO8601，不用prepare时间）
scope:
  mode: create
  base_url: http://127.0.0.1:8001
evaluation:
  freeze_id: 独立冻结题集身份
  sha256: 替换为64位十六进制原始字节摘要
  case_count: 真实题目数量
  model_read_scope: whole_model  # 全模型验收；有界相关资源读取可用 referenced_resources
```

`approved-materials/manifest.json` 使用已有材料合同，按材料 ID 列出相对 `path`、
`source_ref`、`sha256` 及可选 `source_ranges`。准备后从 run 内材料快照接续；原材料、Profile
变化不静默改变原绑定，快照篡改会返回准确错误。当前 Host 路由只接入 `glm-direct`，按
Profile 精确保留模型／effort；新任务使用下述金额模式或明确授权的 usage_only，
不自动降级。历史次数任务沿旧绑定继续，不通过新 run 重置原授权。

`model_read_scope` 默认 `referenced_resources`，核对冻结实际引用中被报告引用的正文。
显式 `whole_model` 用于全模型完整性主张：要求获准本体的无 IRI 过滤资源清单、全部清单
正文／必要映射以及完整关系图；全目标 root 的 ready 自查也采用该范围，局部／待子级
自查保持原有边界。程序只核对证据可用性，语义适用与通过判断仍由 Agent 承担。

### 金额累计与自然回合控制

正常金额任务指定 `authorization.mode: amount` 和稳定 `budget_ref`（相对任务文件解析）。
Host 按真实授权用现有 `modeling_team.task_budget.TaskBudget.create` 创建账本及价表快照，
v5 不自动创建额度、追加授权或静默换价。相同任务的后续 run 继续绑定原账本。
`usage_only` 保留研发用量记录，不执行金额准入。

```yaml
authorization:
  mode: amount
  reference: 当次真实Host授权引用
  budget_ref: /absolute/path/task-budget
```

v5 将实际 Codex 累计通知和传输尝试登记到已有账本。新原生回合前刷新金额、模型／价表
准入及控制状态；已开始回合内的工具、后续请求和压缩自然完成。结束后保存原结果、
刷新金额并在下一活动前暂停。余额可以因该回合尾差变负，实际金额及未知尾差上界照实显示。
重复累计通知、读取及原执行结果复用不会重复扣费。独立评价沿同一预算计量；
Host 用量单列，不扣任务金额。CLI 的 `status`／`budget` 按需刷新，没有新增常驻监视服务。
独立报告纠错延续本人的 native thread，使用前一回合真实累计 counter 作为既有账本的
`cumulative_segment.baseline`，只计新增用量；缺少金额模式基线时返回可恢复错误，不按零估价。

```bash
python -m ontoweave_modeling budget --run-dir /absolute/path/run
python -m ontoweave_modeling budget-add --run-dir /absolute/path/run \
  --authorization-file /absolute/path/approved-addition.json
python -m ontoweave_modeling resume --run-dir /absolute/path/run
```

追加文件沿原账本合同，例如 `{"amount":"1","authorization_id":"实际追加身份",
"authorization_reference":"真实授权依据","continue_authorized":true}`。重试同一追加身份
不重复加款。追加只改变预算状态；已有用户暂停仍需明确 `resume`。缺价或计量异常返回
原类型化反馈，可由 Host 修复后沿原账本接续，不重做已完成回合或已确认应用。
累计金额是指定价表下的用量估算，不等于提供商最终账单；缺失值不补零。

框架正常链为 `prepare → model → apply → self_check → handoff`。工作空间和 checkpoint
保存精确引用，实际应用仍走已有统一图／明确变更、编译器、跨批绑定及 executor；Host worker
使用 backend 环境，不导入旧 CLI 或启动 `TeamRunner`。原始原生事件、返回、用量及 executor
意图／回执各保留原件。缺失业务输入已接入下述最小 HITL 问答与持久等待；完整 P1.3
范围继续按阶段验证。

当次任务的 `instructions` 应采用[有界建模提示](instructions/modeling.md)，并附入适用的
现有统一图／直接变更／语义定义技术合同；只提供合同名称不足以让隔离 Agent 获得其内容。
业务材料继续以 `source_manifest` 的精确 ID 读取。准备好交给 Host 应用的完整变更返回
`proposed`，应用尚未发生不构成 `recoverable_issue`。后续变更复制 Host snapshot 的
`resource_refs` 到 `existing_resource_ref`；`receipt_item_path` 仅为来源位置，不是该绑定
引用的 path，`artifact_ref` 由 Host 解析，无需 Agent 尝试读取同名文件或 MCP resource。
更新／删除把同一实际引用复制到 `target_ref`。关系没有独立资源 IRI，其三元组身份由
Host 从已应用 payload 和真实同批输出保留在绑定元数据；不要把这些字段加进
`target_ref`／`existing_resource_ref`，引用对象仍仅含 `artifact_ref` 和 `path`。
真实任务中的缺口及修复见[推进记录](../../docs/delivery/records/2026-10-29-v5-runtime-capability-progression.md)。

暂停／停止先登记，等待在途原生回合自然结束，不调用 steer／interrupt；已返回候选保留。
`stop` 不会由 `resume` 静默撤销。未知原执行保持 `reconciliation_required`，有原完成事件或
回执时复用原结果；本阶段不承诺所有故障都能自动重连。应用恢复保持原操作身份和原分批，
不把 checkpoint 当外部副作用事务。

独立评价由 `evaluate --package /absolute/path/independent-materials --evaluation-id stable-id`
启动。该包使用材料 manifest，包含同版本原来源和 `frozen-questions`；Host 加入准确实际目标。
评价只获原材料、冻结题集与治理读取，具有独立原生上下文；不收到生产候选、自查或队列输入。
Host 统一统计所有在途角色供暂停／停止判断。私有题目、答案和理由只保存于评价原件，公开反馈
仅投影 verdict、范围及目标身份。格式或必需读取错误可沿同一评价身份重试，保持原冻结标准；
未知在途执行不会借新报告尝试重启。当前工程 fixture 的 PASS 不代表真实语义 PASS。

普通冻结题报告只使用五个逐题字段：index、passed、actual_answer、reason、evidence_iris；
项目自定义 CQ 才使用 CQ 版本及分层能力字段。程序保留严格 JSON 校验并返回解析位置，
不执行报告中的表达式。格式／补读纠错恢复该评价自己的原生上下文，原回合事件单独保留；
题集、来源、目标或必需工件变化不沿用该证明。只有实际 thread 身份相同时才合并自身读取，
累计 token 从前回合真实计数取差，不重复计费。

独立者的 `target` 只携带冻结读取范围，省略写入回执引用；`whole_model` 还省略写入绑定
目录，须从受治理全量清单取得实际资源。引用范围评价仍提供资源 IRI／关系端点等定位字段，
省略执行用 item／change／receipt 字段。完整 handoff、授权和修订核对继续保留原目标。

完整读取按同 ID＋SHA256 的返回字符区间合并。必须检查的额外独立工件用
`--required-artifact material-id` 显式冻结；仅把文件放入包中不会自动增加读取义务。
`read_material` 默认每页 16000 字符，可显式指定 limit；更长材料仍按 next_offset 补读。
PASS 需要本范围来源及实际定义读取完整；缺口可补读或报告 PARTIAL，正文已返回仍由
独立 Agent 判断语义。`whole_model` 需整本体清单、所有正文和完整关系，默认
`referenced_resources` 只核对报告引用的已绑定资源，不能宣称全模型完整。

## 项目自定义 CQ

项目总览支持保存、编辑、停用、选用和 JSON 导入 CQ。只需题干，不要求 Ontology、
答案或切片。公开判定口径与资料引用可稍后补充并确认；私有验收答案继续沿原独立包。
示例种子位于 `examples/llm-access-lab/competency-questions.json`，导入不触发建模或收费。

新任务绑定 `project_ref` 时默认启用项目 CQ；其他任务可显式设置 `custom_cq: true`，
在实际项目建立后读取。旧 binding 不追溯启用，`custom_cq: false` 可明确禁用自动读取。
Host 将选定题固定为 `cq-goals` 材料（类型 competency_goal）；它是目标，不是业务事实。
生产仍须读取原始业务来源。标准草稿不能证明 PASS；Agent 可以通过既有语义记录与 HITL
整理／核对口径，用户在问题编辑中确认可用标准。覆盖用现有 kind=coverage 记录 CQ ID、
负责单元及跨单元整合要求，用户界面不要求切片选择。

自动读取在安全推进边界比较版本，沿 SourceRevisions 排队并保留旧材料和报告；忙碌回合
不被中断，新的问题版本会使旧候选重新核对。手动同步不启动模型：

```bash
scripts/modeling cq-sync --run-dir /absolute/path/to/run
scripts/modeling cq-evaluate --run-dir /absolute/path/to/run --evaluation-id cq-regression-1
```

`cq-sync` 只排队，后续获准推进在自然回合边界生效；stopped run 不被重新打开。
`cq-evaluate` 将当前选定题冻结成追加批次，复用实际 handoff、原始来源与独立只读评价，
保留主冻结题和旧报告。同 evaluation-id 重试复用原题集，题库变化需新的评价身份。
新任务可用 `cq_question_ids: [实际CQ-ID, ...]` 限定本次范围，独立 CQ 验证也可重复传入
`--question-id 实际CQ-ID` 选取本批子集，不必改变项目后续默认选题。
正常授权／预算控制继续适用；本命令不授予启动或恢复权限。

每题绑定 CQ ID、内容版本及摘要，区分 pass、model-recall-insufficient、
question-answer-review、platform-runtime-incomplete，以及模型可回答性、SQL 生成条件、
SQL 实际执行。缺标准或引用无法绑定来源的题保留在分母并待复核；来源缺口不能归因为
模型质量失败。本评价没有 SQL 执行器，只能报告 not_run／blocked，不能宣称实际 SQL PASS。
公开摘要写回匹配版本的项目问题，旧版本结果不覆盖新问题；答案和私有理由保留在原运行。

## 可选生产成员通信与任务卡

本节兼容 peer 配置仅适用于既有单根 binding 或显式 `single-modeler/v1`。默认专职团队
沿上述 role/work_kind 工作树通信；不混挂旧 peer 合同。旧任务可增加 `collaboration`，例如：

```yaml
collaboration:
  peers:
    - agent_id: reviewer
      objective: 按实际收到的请求校验原材料范围，提供有来源的分析并回复发起者。
```

`modeling` 是当前建模工作单元的稳定生产身份；配置中的 peer 同样使用已授权 modeling
模型配置。独立验收不在生产成员列表中，不获得通信／工作卡工具。未配置的任务保留原路径。

生产成员获得 `send_team_message`、`publish_handoff_material`、`read_handoff_material`、
`update_work_card`、`get_work_board`、`resolve_work_request`。普通消息可附固定版本材料
引用及署名 `work_request`（summary、可选 blocking），同一请求在双方卡片关联展示。
本人计划由本人更新，只有发起者判断请求 satisfied／withdrawn；回复不自动满足依赖。
`message_id` 在发送者／run 内稳定，同内容重提复用队列记录，不同内容冲突可纠正。

材料可发布本人分析 `text`，或用 `source_material_id` 冻结获准原文，不需重抄全文。
消息仅携带 object_id／revision／digest 引用，接收方按 offset／limit 字符范围读取；
读取参数的 object_id／revision 在工具 schema 中明确列出，digest 可省略，由工具补全；
显式提供的摘要仍须匹配。消息／材料 ID 是数据库内的不透明标识，不按文件路径限制格式。
材料的新版本不替换已交接旧版本。接收者只能读本人材料或实际收到的对应版本。
同伴消息标记 source=agent，不成为人工答复或新增获准业务事实。

建模 Agent 需要等待协作时返回 `waiting_peer`。当前原生 turn 完成后，LangGraph
`collaborate` 节点按队列执行有输入的 peer，再把回复交给原建模步骤；没有消息时保存等待
并结束，不启动轮询模型。该兼容 peer 模式按消息串行；下述 work_management 工作树支持
独立单元并发及递归。正常输入不
steer／interrupt；工具结束或输出 item 结束不等于整个 turn 结束。程序重建沿原执行登记
和检查点接续，已经确认的应用不重放。已退出的等待仍需显式 resume。

```bash
python -m ontoweave_modeling board --run-dir /path/to/run
python -m ontoweave_modeling board --run-dir /path/to/run --agent-id modeling --revision 1
```

工作卡保存本人当前工作、范围、近期计划、等待说明、成果引用及更新时间；历史版本复用
现有 PostgreSQL 对象版本。指定 revision 读取历史本人卡，关联请求／运行活动仍是当前
投影，不冒充历史快照。无卡如实返回空记录。

通信工具由 Agent 专属 MCP 进程执行；连接配置只挂载到受限工具环境。连接地址在 Host
进入隔离环境前解析，沿已验证 P0 的 hostaddr 路径，避免隔离环境缺 DNS 文件导致失联。

## 多工作单元子集

本节保留原单根工作树示例；新默认已由程序建立专职团队，由 Coordinator 维护专业分派。
新模式如需预配置工作，必须提供相符 role_id/work_kind，不能把旧通用单元当专职配置。
旧模式任务可添加 `work_units` 及 `unit_concurrency` 作为初始工作树，也可用 work_management
让 Agent 按需动态委派。下例只展示最小直接子级：

```yaml
team_contract: single-modeler/v1  # 显式选择本节旧合同，不是新任务默认值
unit_concurrency: 2
work_units:
  - unit_id: installation
    objective: 本单元有界目标及所需人工输入
    instructions: 可选补充说明
  - unit_id: verification
    objective: 可独立推进的核验范围
```

各子级使用独立工作身份、执行目录和 PostgreSQL checkpoint。子级停在 proposal_ready，
由程序发布版本化交接材料给父级；父级按需读取原文、材料及实际人工答复后统一应用模型。
局部 HITL 不暂停其他单元；在其他单元仍忙碌时，新答复也可恢复其目标单元。
没有新输入时静止，resume 从原记录继续，不重放已完成候选或已确认应用。
现有 status 返回 units；questions 显示请求单元，reply 按请求自动路由；主动补充可使用：

```bash
python -m ontoweave_modeling input --run-dir /absolute/path/run \
  --unit-id installation --text '本单元的实际补充'
```

快照同时保留各子图 checkpoint。动态递归使用相同执行图；大型业务的语义质量仍另按
P2 验证；[工程及真实运行记录](../../docs/delivery/records/2026-10-29-v5-multi-unit-delivery.md)
区分已实现机制与实际父级闭环的验证范围。测试阶段可按用户授权构造并署名 HITL 答复。
父级可按真实依赖分批应用；后续提交前从原快照恢复并关闭此前已确认完成的 Session。
历史明确未写入的尝试不阻止收口，结果未知的写入继续按原身份对账。

## 最小共享业务记忆

本节是单根合同的旧记忆入口；默认专职团队用 semantic workspace，不挂载这些旧工具。
旧 Task 增加 `shared_memory: true` 后，生产成员可调用 `write_memory`、`read_memory`、
`search_memory`；可以与 collaboration 同时使用，也可以只供单个成员换会话接续。
记录包含 entry_id、kind、title、body、source_refs；作者、更新时间和 revision 由程序保存。
kind 是普通标签，建议 judgment／decision／open_item，不强制枚举或固定业务步骤。

用关键词查到 entry_id 后读取完整记录，保留正文中的条件、排除项及未知。更新使用读取的
revision 作为顶层 expected_revision；冲突直接提供当前内容供 Agent 合并。相同正文不
重复生成版本。第一版按 task 共享，复用已有 PostgreSQL 对象版本；不另建向量库或记忆服务。
记忆是业务理解，不代表已应用模型或人工确认，实际应用／自查仍走原接口。

## Host 命名检查点快照

```bash
python -m ontoweave_modeling snapshot-save --run-dir /path/to/run --name before-review
python -m ontoweave_modeling snapshot-list --run-dir /path/to/run
python -m ontoweave_modeling snapshot-show --run-dir /path/to/run --snapshot before-review
python -m ontoweave_modeling snapshot-diff --run-dir /path/to/run --before before-review --after after-review
```

快照保存工作空间内容／版本、工作卡和队列、LangGraph checkpoint 引用、执行引用、
保存时源码摘要及实际模型上下文／版本。源码摘要不代表已启动进程加载的代码版本。
文件在 run 的 snapshots 目录，快照名是标签，不作为
文件路径；程序生成唯一文件身份并保留旧内容。可在 Agent 忙碌时观察保存，不要求暂停。
只读 list／show／diff 直接读取保存文件，不要求原任务、原材料或当前工作流版本仍能加载。

各组件保留各自版本，不声称跨存储全局事务。模型读取不可用时保存原引用和读取错误；
默认快照用于观察、复盘与对比；下述 include-platform／snapshot-fork 另接真实数据捕获及
显式源归档分叉，不将默认引用快照称作平台数据备份，也不执行原地模型回滚。
设计见[最小记忆与快照](../../docs/delivery/designs/2026-10-29-v5-memory-snapshot-minimal-design.md)。

## 最小 HITL：问题、答复与主动输入

Agent 回合结束返回 `waiting_input` 和 `human_requests`，每个问题包含 `question`、
`reason`、`impact`。程序保存请求、版本、来源和原步骤后进入 LangGraph 等待节点，
不增加每步审批或常驻 Delivery LLM。工程与真实授权代答证据见
[最小 HITL 交付记录](../../docs/delivery/records/2026-10-29-v5-minimal-hitl-delivery.md)。

在上述锁定 v5 环境中执行，替换为当前实际 run、请求和消息身份：

```bash
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling questions \
  --run-dir workspaces/v5-runs/my-run
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling reply \
  --run-dir workspaces/v5-runs/my-run --request-id human-request-from-questions \
  --request-revision 1 --message-id stable-user-message-id \
  --author user --text-file /absolute/path/answer.txt
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling resume \
  --run-dir workspaces/v5-runs/my-run
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling input \
  --run-dir workspaces/v5-runs/my-run --message-id another-stable-message-id \
  --text '用户主动补充的内容'
```

`questions` 展示原问题、版本、答复和状态，不调用模型。`reply` 关联原请求；`input`
无需先有问题。两者支持 `--text`／`--text-file`、`--author`、`--message-id`、`--partial`。
作者是本机操作者声明的来源标签，不是新增身份认证。未知提交结果重试时复用消息 ID；
同身份不同内容返回冲突。授权宿主代答时保留用户原授权及实际代答作者。

答复先入队；busy 时不打断当前回合，下一适用回合消费。已退出等待的进程用 resume
恢复原 run，没有后台轮询模型服务。收到／交付／消费都不自动关闭问题；Agent 使用
`resolved_request_ids` 明确确认匹配非部分答复解决了哪些请求。重复确认已解决请求为
幂等，其他问题保持未决；基线变化保留旧问题／答复，刷新实际基线供 Agent 判断适用性。

重启／checkpoint 重入复用原始执行、问答及应用身份；应用后等待不重放创建。停止或
交接后的新输入不静默重新打开目标。只读评价获得冻结的有归属人工材料并必须实际读取，
不消费生产输入队列，也不获得写入权限。

## 显式材料修订与动态工作树

`source-revise --run-dir RUN --change-file CHANGE.json` 接收下一版完整材料包。变化文件包含
`change_id`、相对路径 `materials`、`reason`、可选 `affected_units` 及下一冻结 `evaluation`。
旧材料、绑定版本、原生回执和模型身份保留；已完成单元可按明确影响范围重新进入，未变
成果复用。忙碌时先入队，在自然回合结束后处理，防止旧候选继续应用；`resume` 沿原 run
激活待处理变化。材料撤回不自动证明原业务判断为假。

旧单根任务设置 `work_management: true` 可从零个预设单元开始；专职新任务自动建立必需
职责，Coordinator 决定业务范围与后续专业分派。两者均使用 `delegate_work`、
`get_work_tree`、`reopen_work_unit`、`update_work_unit`。已有 `work_units` 也进入同一工作树；
子级可以继续委派，依赖就绪才组合，根单元是唯一模型写方。委派后返回 `waiting_children`，
父级按需读取直接子级成果并保留未分配范围。`get_work_tree` 默认返回本层直接子级，
可指定 `parent_id` 和分页下钻。显式重开同时使祖先重新整合，兄弟成果保留。

当前真实验证及尚未证明范围见[持续开发记录](../../docs/delivery/records/2026-10-29-v5-autonomous-progression.md)。

任务设置 `semantic_workspace: true` 可使用 `write_semantic_record`、`read_semantic_record`、
`search_semantic_records`、`get_modeling_context` 保存／查找命题、解释、决定、定义、覆盖、
未决项与摘要。依赖复制读取回执的完整 `reference`（包括 scope 和 revision）；摘要按
这些明确依赖显示待重审，不把材料撤回判断为业务事实为假。各自的 review、cognition、
expression、work、applicability 独立记录，应用及独立验收不由笔记赋值。

Host 显式绑定 `project_ref` 或平台实际创建项目并完成运行期关联后，语义记录及共享记忆
工具可指定 `scope="project"`，在获准
新任务／run 中复用同一项目的判断；默认仍为任务范围。新上下文使用 get_modeling_context
获得有界导航，再按需读原文和完整记录，不能把摘要作为当前实际模型的证明。

实际已有模型满足来源时可返回 `no_change`，不提交空写入，仍进行治理自查和独立交接。
技术纠正会获得上版候选内容或固定版本材料引用；修原稿而非只按错误路径重建全部候选。
原生启动前的已知失败与启动后的未知分别处理；HTTP 429 在自然边界暂停下一回合，
仅凭 HTTP 状态不声称已确认提供商五小时窗口或重置时间。

`snapshot-save --include-platform` 额外保存实际平台数据，随后可用
`snapshot-fork --snapshot ID --new-run-dir DIR --new-run-id ID --fork-reason TEXT
--authorization-reference REF --archive-source` 准备新项目接续。该显式操作会封存源项目。
原任务／预算关联保持，以 workspace_ref 隔离新控制和认知记录；新 run 使用 resume 真实
启动，重新自查和验收。普通观察快照可继续查看／比较；数据分叉需使用带平台数据的快照。
具体取舍见[复用说明](../../docs/research/2026-10-30-v5-snapshot-fork-reuse.md)。
新 fork 会把保存时图中的显式原生资源 ID 按实际目标本体交接到 Host bindings，
保留快照来源摘要，供复用已有类和关系端点；不从 IRI 后缀猜 ID，也不把它当成新应用回执。
已完成的旧 fork 不自动补写身份，缺少唯一原生身份的内容仍按既有可恢复反馈处理。
真实增量写入及接续的验证边界见[本轮记录](../../docs/research/2026-10-30-v5-fork-native-binding-delivery.md)。

## 总览与分层独立评价

`overview-refresh --overview-id ID --topic TEXT --view consumer|user` 使用全新只读上下文，
仅从获准实际模型生成总体／主题导航、精确资源引用、未知与限制；sections 支持可选
递归 children，同一实际 IRI 可跨主题引用，叶子同样须有真实读取。当前 user 仍为模型投影，
不代表候选／工作／验收多截止点用户视图已完成。`overview-show` 在读取前
核对当前访问及模型版本；来源／依赖／模型变化使相关记录 needs_review，旧依据保留。
生成期间变化的结果不标为当前。消费者视图不挂载生产笔记或隐藏验收材料。

`evaluate --scope-file SCOPE.json` 可在原主冻结下执行独立有界或追加评价。范围文件包含：

```json
{
  "scope_id": "bounded-unit",
  "base_freeze_id": "original-primary-freeze",
  "source_ids": ["approved-material-id"],
  "objective": "本次范围及与父级的连接",
  "evaluation": {"freeze_id": "scoped-freeze", "sha256": "实际题集摘要", "case_count": 2}
}
```

评价包只需选定原始依据、冻结题及所需待验产物，目标仍是确切实际模型。公开报告带范围
及主冻结引用；原主报告保留。父级不能以子级分数代替整体规则和原始依据核对。
`--required-artifact ID` 保证待验记忆、摘要或公开子报告被实际读取；它们不成为模型事实来源。

多个获准 Ontology 的新建变更使用 WorkResult `ontology_targets: {change_id: ontology_id}`；
更新通过实际 target_ref 继承目标。未选明的多本体创建返回可修正反馈，不静默写入第一个。
新任务、历史迁移及收尾的完整操作边界见 [Host runbook](../../skills/modeling-dev-loop/references/v5-runbook.md)。

## 可选过程评价（R5.0-011）

默认关闭，已有 run 不自动启用。新 Task 可设置
`process_evaluation: {enabled: true, points: [cq, slicing, integration]}`。
开关不授权收费调用或新增预算；托管评价使用原任务 acceptance 模型及预算，执行用途为
`process_evaluation`，不计为建模轮次或 semantic start。正式 `evaluate` 的资格保持。

Host 在获准阶段产物提交后，显式提交版本引用，不依据聊天或回合结束猜测阶段：

```bash
scripts/modeling process-configure --run-dir RUN --enabled true --point cq --point slicing --point integration
scripts/modeling process-submit --run-dir RUN --submission-file stage.json
scripts/modeling process-run --run-dir RUN --binding-digest RETURNED_DIGEST
scripts/modeling process-report --run-dir RUN --production-status closed
scripts/modeling process-configure --run-dir RUN --enabled false
```

`stage.json` 示例（引用使用工作空间返回的原值）：

```json
{
  "point": "cq",
  "scope": "整体业务目标及未分派范围",
  "goal": "核对获准来源中的条件、例外及跨单元问题覆盖",
  "unit_ids": [],
  "source_ids": ["approved-source"],
  "artifact_refs": [{"object_id": "semantic:cq-plan", "revision": 1, "digest": "RETURNED_DIGEST"}]
}
```

首期采用 Host 显式提交及独立 worker 命令，不新增常驻调度器。生产推进不等待 worker；
Host 可并行执行 `process-run`。来源只来自 Task source manifest，产物只允许工作空间的
生产记录、候选、交接材料和工作树精确版本，不读取正式隐藏题。CQ／切片只需材料；
整合提交抓取实际修订，执行时须有该修订实际正文及治理读取。默认引用快照不是原子备份，
旧正文不可得时登记失败／未验证，不用当前模型补历史。报告和读取只保存到独立诊断侧，
不交给生产或正式验收。

相同绑定重放复用记录；显式复评可提交新的 `reevaluation_id`。失败可用原 digest 加
`process-run --retry` 修正，保留每次执行证据。未知在途沿原执行身份对账，不重启调用。
停用取消未开始队列，已开始回合自然收尾；重启／启用不恢复取消项，补评须显式复评。
Task pause／stop 和金额预算准入仍优先；停用不免除已发生用量或在途收尾。

JSON／Markdown 原件位于 `RUN/process-evaluations/summary-NNNN.*`，工作空间保留版本。
生产返回、pause／stop 自动生成阶段汇总；失败提前收口亦可用 `process-report` 显式记录。
未观察阶段保留三类覆盖分母，未知不计零分，晚到结果新增汇总且保留生产终态。
Host 提交前核对 point、scope、goal 与当前产物版本一致；误提交保留原件但不运行，
另行提交正确绑定。失败/停止收口使用相应 production-status，不把生命周期结束写成
业务或模型验收通过；过程评分不回灌为生产答案。
报告保留逐维结果、关键差距、未评范围、冻结配置、原任务账本计价单元及原始用量引用；
无计价单元时成本为未知，不补零。跨配置／来源／范围不自动算分差。

`process-evaluation/v2` 按观察点区分证据：CQ 评价问题／能力目标，切片评价方案，
两者不要求已应用模型或执行回执；整合才要求绑定修订的实际治理正文。缺少必要绑定
材料记未验证，不能推断生产没有该内容；能力目标附答案也不能直接当作盲测题缺陷。
重试的 `evaluator_feedback` 只用于修正评价者自己的报告，不是生产或 CQ 答案失败证据。

满意度读取每维 `status`、`score`、`priority`：低于 3 分或声明非 `none` 的缺口优先级
表示有差距；没有已证实缺口但必要检查未完成则为未验证。`gap`／`key_gaps` 是解释，
不按说明文字是否非空判定缺口。任何已证实缺口须落到相应维度并标明非 `none` 优先级；
无缺口用 `gap=""`、`key_gaps=[]`，正常边界注记放可选 `boundary_notes`，不混入
仅记录本阶段必需未检查项的 `unexamined`。报告解析使用本报告的必需形状选择唯一对象，
正文中的 `{}` 不算另一份报告，真正的多个不同报告仍返回可纠正错误。

准则变化后不使用新准则静默评分旧绑定；旧在途先沿原执行对账，后续需显式重新提交
同一来源／产物版本以取得新准则绑定，原失败和已完成报告保持。修复验证及边界见
[真实运行缺陷修复记录](../../docs/delivery/test-docs/2026-11-03-process-evaluation-live-repairs.md)。
工程合同通过不代表评分校准、真实任务采用或净降耗通过，见
[独立测试记录](../../docs/delivery/test-docs/2026-11-03-r5-0-011-independent-tests.md)。
