# v5 P0 Codex 接入验证记录

日期：2026-10-28。归属：[R5.0-001 F8](../../requirements/requirements-v5.0.md#r5-0-001)、
[实施计划 P0](../implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#5-p0在全面改造前验证什么)。

**当前结论：47 项开发测试通过，独立工程第 2 轮 PASS；主要 P0 真实链路已验证，隔离平台目标的独立评价为 6/6 PASS。**
完整计量覆盖仍为 PARTIAL，不把该小范围结果升级为完整 P0／v5 验收或 P1 生产实现。
用户已确认自然工具回合加程序校验，并明确本任务不受原 3 元额度限制；原预算与失败证据保留。
后续统计允许重做，旧统计组件不成为当前任务的前置硬门。本批在选型与证据结论处按用户要求暂停；
P1—P4 与默认入口尚未切换。新增证据见文末“继续授权后的真实集成”。
首批 `0290bac` 的 9 项无推理基线及原始失败记录保留。

## 授权与实现范围

用户追加授权按计划开始 v5 底座技术切换，要求优雅架构实现现有功能，遇到需知晓或决策的事项暂停。
本批从 P0 开始，以实际 SDK 接入消除配置和隔离假设；不提前开发 P1—P4。
首批 `0290bac` 没有创建任务预算；本次后续授权已建立独立 3 元预算，没有恢复旧任务或占用旧任务额度。

实施前 HEAD 为 `1edb162`。新增[独立 Python 包](../../../modeling_team/v5/README.md)
`ontoweave_modeling`；它不导入会立即加载旧 Runner 的 `modeling_team.__init__`。
使用 SDK 自带传输和类型解析，没有复制旧 Runner 或手写第二套 JSON-RPC 客户端。
namespace 隔离布局沿用现有实现经验，本次无推理入口额外禁用网络。

当前改动不改变后端、前端、平台合同、活跃运行配置、数据库或默认任务入口，
无需重启服务。原有 GraphRAG 文档的三处未提交改动保持。

## 首批无推理基线环境（0290bac）

| 项目 | 本批实际值与边界 |
| --- | --- |
| Python | 3.12.3；项目固定 3.12 系列，未声明其他 Python 版本实测通过。 |
| Python SDK | `openai-codex==0.163.0`。 |
| SDK 绑定运行时 | `openai-codex-cli-bin==0.163.0`，实际执行返回 `codex-cli 0.163.0`。 |
| CLI SHA-256 | `399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`。 |
| 全局 CLI | `0.165.0`，未用于本批 SDK 测试，未升级或替换。 |
| 模型配置 | 从现有 `glm-flash-low.yaml` 的 modeling 角色读取；真实 thread 返回 `glm-direct / glm-5.3-flash / low`。只证明配置采用，不证明模型执行。 |
| 测试／格式工具 | pytest 9.1.1、Ruff 0.17.3。 |
| 环境与依赖 | `workspaces/v5-codex-p0/.venv`；项目 `uv.lock` 锁定直接及传递依赖，使用 `uv sync --locked`。 |
| 首批未接入 | LangGraph／PostgreSQL checkpointer、业务工作空间、真实 MCP、预算主账、真实平台及独立评价；后续进展见文末。 |

SDK 绑定 CLI 的官方合同见[Codex SDK 文档](https://learn.chatgpt.com/docs/codex-sdk)。
本批依赖安装后通过实际二进制及 RPC 核对，没有借用全局 CLI 的旧 schema 结论。
初次依赖安装下载了 SDK 绑定 CLI；随后锁定项目环境复用已安装的同版本包，
取消了重复环境的 CLI 下载。复跑以锁文件与上述明确环境为准。

## 测试轮次与真实观察

| 轮次 | 结果 | 发现与处置 |
| --- | --- | --- |
| 开发第 1 轮 | 8 PASS／1 FAIL | 真实 SDK 启动、绑定读回和 namespace 隔离通过；能力清单只读取了前 100 项，`nextCursor=100`，导致 `goals` 尚未出现在结果中。 |
| 开发第 2 轮 | 9 PASS／0 FAIL／0 SKIP | 接续读取全部分页后通过。没有删减所需能力断言或增加 run 守卫。 |
| SDK setup 第 1／2 轮 | 1 FAIL → 1 PASS | `skills/config/write` 需要路径的序列化值，不能使用 SDK RootModel 的 `str()` 表示；修正后真实 SDK 证实系统 Skills 均在 thread 创建前关闭。 |
| 开发第 3 轮 | 25 PASS／0 FAIL | 增加 MCP 材料范围、版本和结果解析校验；1 条第三方 Pydantic lifespan 注解警告，不影响本轮调用。 |
| 开发第 4／5 轮 | 均 27 PASS／0 FAIL | 增加真实 namespace 工具名及本地拒绝先于上游尝试的回归；第 5 轮覆盖最终格式及显式 subprocess 检查配置，同样 1 条上述警告。 |
| 命令行入口 | PASS（无推理范围） | 使用仓库实际模型 Profile 执行；完整读取 175 项能力，`nextCursor=null`，临时 thread 的 turns 为空。 |

[测试源码](../../../modeling_team/v5/tests/test_preflight.py)覆盖：独立包不加载旧 Runner、
角色配置精确读取、三种缺失／无效 effort、显式无凭据配置、真实 Linux namespace
隐藏宿主输入、真实 SDK／CLI 配置读回，以及已有证据目录不被覆盖。

namespace 实测中，宿主测试材料、父目录 AGENTS、宿主环境变量和宿主凭据均不可见；
仅有隔离 loopback 接口，没有宿主网络接口。SDK 子进程只运行初始化与读取类 RPC，
未调用 `turn/start`，模型地址也不可达。该结果不等于真实生产／评价工具授权通过。

**首批实测发现（后续已窄修）**：空 home 仍自动安装并启用 `imagegen`、`openai-docs`、
`review-agent`、`skill-creator`、`skill-installer` 五个系统 Skills。
它们来自运行时内置内容，不是读到了宿主 Skills。后续真实 Agent 已通过公开
`skills/config/write` 在新 thread 前关闭这 5 个 Skills，并保留清单及实际出站记录；
完整 V2 仍需生产／评价隔离与越权反例，不能只据此放行。

## 命令与原始证据

在仓库根目录执行，先设置本批隔离环境：

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/workspaces/v5-codex-p0/.venv"
uv sync --locked --project modeling_team/v5 --group dev
uv run --locked --project modeling_team/v5 pytest -q \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests \
  --junitxml=workspaces/v5-codex-p0/developer-round2.xml
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling.preflight \
  --model-profile modeling_team/model-profiles/glm-flash-low.yaml --role modeling \
  --output-dir workspaces/v5-codex-p0/runtime-baseline-001
uv run --locked --project modeling_team/v5 ruff check modeling_team/v5/src modeling_team/v5/tests
uv run --locked --project modeling_team/v5 ruff format --check modeling_team/v5/src modeling_team/v5/tests
uv lock --check --project modeling_team/v5
```

上述命令行的输出目录已存在，复跑时须换用新目录以保留原件。

gitignored 证据目录为 `workspaces/v5-codex-p0/`：

- `developer-round1.log`、`developer-round1.xml` 及复制保留的 `developer-round1-preflight.json`。
- `developer-round2.log`、`developer-round2.xml`。
- `runtime-baseline-001.log` 及 `runtime-baseline-001/preflight.json`：版本、哈希、
  配置层、实际绑定、完整能力清单、Skills 与空 MCP 清单。

SDK 读取证据和测试结果不作为独立验收。已有 LangGraph／SQLite 风险实验仍按
[原范围](2026-10-27-v5-langgraph-risk-validation.md)复用，本批未重复执行。

首批 Ruff 检查、100 列格式检查和锁文件一致性检查通过；4 份相关 Markdown 的 63 个本地链接、
14 个锚点及围栏／空白检查通过。GitNexus 暂存检查识别 10 个变更文件，未映射出符号；
索引落后 HEAD 518 个提交，因此该结果不提供图影响覆盖。本批按源码、导入和调用点核对，
变更只接入新包及其自有测试，不改变旧入口的调用关系。

## 剩余范围与暂停点

本节及下节记录首批提交时的历史状态，后续进展以文末续记为准。

| 项目 | 当前证据状态 |
| --- | --- |
| V1 | SDK、真实模型／MCP、可恢复工具错误已有证据；`outputSchema` 回合存在缺口，流式错误尚未验证。 |
| V2 | 宿主输入隔离、Skills 关闭与实际出站有实测；生产／评价独立上下文及完整越权反例未验证。 |
| V3—V8 | 未在本批执行；不得以本批 9 项测试关闭计量、控制、压缩、协作、平台故障对账或独立交接。 |
| 选型结论 | Codex 仍暂定；未达到进入 P1 全面实现的放行条件。 |

本次 3 元授权已到位，不需要重新申请原预算。下一步是确认下面的执行结果合同，
恢复同一预算后继续 P0，P1—P4 和默认入口保持待放行。

## 授权后真实验证与决策暂停

### 授权、实现与计量

用户回复“同意授权”，承接当次明确提出的 P0、`glm-direct / glm-5.3-flash / low`、
独立人民币 3 元及生产／独立评价／失败恢复范围。Host 已建立：

- 原任务：`v5-codex-p0-20261028`。
- 稳定预算：`workspaces/v5-codex-p0/budget`；`resource-authorization.json` 明确 `mode=amount`。
- 价表：沿现有 `user-20261020` 快照，未追加金额或换模型。

新增有界 SDK Agent、manifest 限定的只读 MCP 材料工具、真实出站观察及 JSON 结果校验。
本次补充锁定 MCP 1.28.0、jsonschema 4.26.0，SDK／CLI 仍为同一 0.163.0，
Python 仍为 3.12.3。LangGraph／PostgreSQL 实验尚未进入执行；相关未使用候选依赖已移出本批锁定范围。
Host 试验桥接复用原 `TaskBudget`、`ActivityRecorder`、`NumericReceiptWriter` 和 provider proxy；
未另建费用总账，也未将旧 Runner 包装为执行节点。该 Host 桥接目前仍导入旧包的工具模块，
独立 Agent 包本身不导入旧 Runner；不将本原型宣称为生产依赖切分已完成。

材料沿计划使用最小安装链公开源，SHA-256 为
`ac3d7f91620f292b2a3dcd64d218b4f8d482353b96f5be4c3955e1318a090566`，509 字符。
未读取隐藏题。当前属于已知基准的接入回归，不是盲测或独立语义验收。

### 真实回合及首阻塞

| 目录 | 实际观察 | 结论与处理 |
| --- | --- | --- |
| `v1-live-001` | SDK Skill 路径序列化错误，在推理前失败。 | `platform-contract`；取路径的 JSON 值后通过 SDK setup 回归，无上游调用。 |
| `v1-live-002` | 出站工具为 namespace，而初版本地检查按扁平名字判断；30 次请求均在上游前被本地拒绝。 | `platform-contract`；修正 namespace 识别，将本地拒绝放到 attempt_start 前。原错误记录保留，见下述对账。 |
| `v1-live-003` | 强制 `outputSchema`，1 次上游请求；没有 MCP 调用，却返回声称见过材料错误的 JSON。 | V1 未通过；不能把 native completed 或 schema 合法当实际读取成立。 |
| `v1-live-004` | 关闭 `outputSchema` 后，模型实际尝试工具；材料工具被 MCP 审批层拒绝，资源／模板查询返回空。 | `platform-contract`；为真实只读工具补充 annotation 及仅该工具的获准审批配置。 |
| `v1-live-005` | 3 次上游请求；实际调用 `read_material(missing)` 获得可恢复 `material_not_found`，再实际读取 `scenario`；返回叙述及一个 JSON 块。 | 正常工具循环与错误纠正有真实证据。离线程序从原返回中提取 JSON，并通过同一结构 schema；未修改任何业务内容。 |
| `v1-live-006` | 相同配置、材料、模型、effort 和提示正文，重新启用 `outputSchema`；1 次上游请求，无 MCP 调用，再次声称已有材料错误。 | 当前组合的工具／结构化结果行为仍有缺口；按用户要求暂停。 |

首次真实上游请求时间为 **2026-10-28 03:44:32 UTC**。共 4 个真实 native turn、9 次上游请求；
这些是 P0 接入活动，没有创建平台生产 run、应用模型或产生正式语义验收结论。

`005` 与 `006` 的首请求在移除消息 ID、缓存键和客户端身份后，提示正文、工具 schema、
模型及 reasoning 配置一致；可观察的推理设置差别为 `text.format=json_schema`。
本证据说明当前组合存在需处理的行为差异，**不证明所有模型或 Codex 普遍不支持该组合**，
也尚未将根因确定到 provider、harness 或模型。当前首阻塞按执行层集成问题
`runtime/infrastructure` 保留，不推导本体质量结论。

工具审批采用公开的
[`mcp_servers.<id>.tools.<tool>.approval_mode`](https://learn.chatgpt.com/docs/config-file/config-reference)
配置；只为允许清单中的 `read_material` 设置 `approve`，工具实现本身只读且声明
`readOnlyHint=true`。未知 native 审批仍拒绝。实际请求只含该材料工具及读取同一 MCP
server 的三个通用资源辅助函数；server 的资源及模板清单均为空，没有加入文件、Shell 或写工具。

### 本地拒绝对账与当前预算

`002` 初版把本地拒绝错误登记为 transport_error，导致主账进入缺测暂停。
Host 根据原代码、全部原始出站请求和未进入上游的路径证据，向原 append-only 流追加
`not_admitted` 更正，并保留原失败、原身份和更正依据；没有伪造 token=0 的数值回执，
没有删除失败文件、换预算或重置成本。原主账在缺测恢复后沿原授权继续。
新增真实 HTTP 回归确认：本地拒绝只产生 not_admitted，不产生 attempt_start 或上游转发。

当前主账估算 **¥0.00987516**，剩余 **¥2.99012484**；原授权仍为 ¥3。
native 累计来源按 thread 去重后的字段为：输入 9,119、其中缓存输入 6,208、输出 1,710，
其中推理输出 85。缓存为输入子集、推理为输出子集，没有重复相加。
这只是已观察调用按价表的估算，不是供应商最终账单，也不等于完整 V3 已通过。
外部 Host 及未接线辅助用量分别保留 unknown，不扣任务金额。

所有本次 SDK／namespace 进程已结束，在途与待结算均为 0；原预算记录
`host_decision_pending`，`admission_open=false`、`control_status=paused_confirmed`。
未启动 V3—V8 的进一步实验，没有平台写入或待处理业务资源。

### 待用户确认的结果合同

建议：保留自然工具回合，允许其返回裸 JSON 或唯一显式 JSON 块，由程序执行 JSON／schema
校验。缺失、歧义或类型错误返回可恢复反馈；不修补业务事实，也不以格式通过代替实际工具读取。
这一最小候选已在真实 `005` 返回上完成离线结构验证。

另一选择是工具回合后再用单独 native turn 强制格式；它会增加模型往返和费用，当前没有实现或实测。
最终采用仍待用户确认；暂停期间不继续收费调用，不进入 P1。

### 新增证据和复跑入口

新增 `agent-setup-round1/2`、`developer-round3/4/5` 的日志与 JUnit；上述 `v1-live-001—006`
目录包含生效配置、执行绑定、出站请求、原生事件、用量、结果及预算状态。
`decision-evidence/` 保留原结果结构校验、去身份前后请求比较及 `pause-summary.json`。

真实探针命令如下，**仅在原暂停已按用户确认解除后执行**，每次仍用新证据目录：

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/workspaces/v5-codex-p0/.venv"
uv run --locked --project modeling_team/v5 python modeling_team/v5/scripts/live_probe.py \
  --budget-ref workspaces/v5-codex-p0/budget \
  --output-dir workspaces/v5-codex-p0/v1-live-next --plain-output
```

此命令使用真实模型并计入原预算；`--plain-output` 是已验证的对照候选，未设置时仍复现
SDK `outputSchema` 方式。CLI 分别展示 native 状态和结果结构状态，均不代表语义验收。

本次最终 Ruff、格式、锁文件及 diff 空白检查通过；4 份文档的 70 个本地链接、18 个锚点
检查通过。GitNexus 暂存检查识别 14 个文件，未映射出符号，索引滞后 520 个提交；
本次按新包源码及直接调用点确认范围，不宣称图影响覆盖。后端／前端和共享运行配置未变，
没有重启服务。所有无关 GraphRAG 改动及并行提交的记忆方案研究保持。

## 继续授权后的真实集成

### 授权、依赖和责任边界

用户确认采用自然工具回合与程序结构校验，明确“本任务中无需考虑额度消耗，后续额度统计能力也可能需要重新实现”，
随后再次要求继续。稳定任务仍为 `v5-codex-p0-20261028`；
`workspaces/v5-codex-p0/execution-authorization.json` 保存该授权，原 3 元预算不删除、不重置或伪装为追加金额。
后续 Host 探针保留原始用量、出站、执行绑定和自然回合事件，以 `usage_only` 执行。
这不取消其他任务的预算合同，也不扩大业务来源或模型范围。

SDK／CLI 仍为 0.163.0，全部真实 Agent 为 `glm-direct / glm-5.3-flash / low`。
新增锁定 LangGraph 1.2.18、langgraph-checkpoint-postgres 3.2.0、psycopg 3.3.6；
工作空间与 checkpointer 复用现有 PostgreSQL 的独立 `v5_p0_20261028` schema。
生产包不导入旧 Runner；Host-only 探针仍暂时导入已验收的旧编译、应用、生命周期和读取工具，
不将这种试验复用宣称为 P1 的依赖切分已完成。后端、前端、共享服务配置均未修改，无需重启。

最小业务来源仍为原 509 字符公开材料。实际模型由隔离 Agent 生成定义计划，Host 只绑定真实回执身份；
未代写业务定义或从隐藏题生成模型。最终平台目标：Project `1914d037-3024-4cb1-96d4-1dd25af8528b`，
Ontology `1715cc34-391f-490e-b451-1fb67eaacd6b`，model revision **2**。

### 逐项实证

| 项目 | 当前实际证据与边界 |
| --- | --- |
| V1 | `v1-live-007` 采用已确认的自然回合方案；`stream-live-001/002` 在实际上游 HTTP 200 后注入客户端 SSE 错误，首回合 failed，同一原生 thread 后续 completed。未上报的失败响应用量保持 unknown。 |
| V2 | `isolation-live-002`：生产读取评价私有 canary 被拒，评价尝试写 workspace 被拒，受保护对象 revision 未变；canary 未进入生产出站及结果。平台评价另用 `read` key，仅开放获准材料与固定授权范围的查询工具。 |
| V3 | 所有探针保留任务、角色、native thread／turn、provider/model/effort、原始累计快照及 provider 尝试。已去重汇总已知 token；完整金额、失败缺测、平台辅助推理和迟到数据对账仍 PARTIAL，不报完整费用／预算验收 PASS。用户已取消本任务额度门，后续统计重实现不阻塞本批试验。 |
| V4 | `control-live-001`：A/B 两成员忙碌时输入、暂停及模拟预算关闭信号只登记排队；原生回合正常结束，全部成员结束后才 settled，恢复后原消息实际送达并消费。停止也在自然回合后生效，未调用 steer／interrupt。模拟预算信号不冒充真实金额耗尽。 |
| V5 | `context-live-001` 的 108,509 字符工具结果触发本地压缩，记录 2 个压缩相关事件；Agent 按 source_ranges 在 offset 50,000 补读完整业务段。证明实际压缩与补读链路；不外推成大型业务记忆保真专项已验收。 |
| V6 | `parallel-live-002`：两个真实 Agent 区间重叠，A 等待时 B 跨步骤完成并发布审阅。独立进程从 PostgreSQL pending wait 接续，仍使用原两条 native thread；A 实际读取 B 的 revision 1／2，输入主题变化使回答变化，A 原业务 revision 仍为 1。 |
| V7 | 正常实际应用与治理读回完成；四个故障窗口见下表。业务内容与执行 checkpoint 权威分离，不能用恢复 graph 成功替代平台结果。 |
| V8 | 独立侧预先冻结 6 题，最终 `acceptance-live-003` 在新隔离上下文实际读取材料、题集、目标和当前平台，绑定 revision 2，完整 6/6 PASS。评价无生产创建／继续／修复能力；此为 P0 代表性交接，非完整 P1、L2 或 v5 验收。 |

### 平台故障窗口

故障只注入本批自有客户端边界，平台进程和现有业务资源不受故障注入。
外层使用真实 PostgreSQL checkpointer，每个 initial 与 resume 均为独立进程。

| 目录 | 首段与重建后的实际结果 |
| --- | --- |
| `platform-checkpoint-001` | 定义 Batch 实际 applied 后，节点在 checkpoint 保存前失败；重建后复用原回执，定义未重提，随后只提交关系 Batch。共 2 个实际成功 Batch。 |
| `platform-response-001` | 实际应用后丢失客户端响应，并使首段对账读暂不可用，结果 uncertain；重建后按原身份找到成功 Batch，定义未重提，再完成关系。共 2 个实际成功 Batch。 |
| `platform-not-written-001` | 注入发送前传输丢失，执行侧保留 uncertain；重建后完整清单确认原操作未写入，沿原 envelope 应用并完成关系。最初 1 次未派发，最终 2 个成功 Batch。 |
| `platform-partial-001` | 第一批实际 applied，第二批在发送前明确拒绝。冻结原 `[1,1]` 分批后重建：复用第一批回执，0 次新提交，仍为 partial。第二批需要明确纠正请求；未补齐、未伪装为整体恢复完成。 |

原 Batch／Attempt、请求、intent、receipt、治理读回、pending checkpoint 与收尾原件均保留在上述目录。
全部 5 个测试 scope 已核对 Session terminal、无在途 Attempt，建模和 bootstrap 管理 key 已撤销；
独立评价 read key 另有实际撤销回执。4 个完整目标和 1 个部分成功目标均保留，不删除历史效果。

### 失败、修复与独立测试

- `parallel-live-001` 曾因隔离环境没有 DNS 文件而无法解析 Host 配置的 `localhost`。Host 在挂载数据库配置前解析获准端点地址，保持工具隔离；新增真实 SDK→隔离 MCP→PostgreSQL 的成功与越权测试。
  原失败保留，后续 `parallel-live-002` 实际工具调用均 completed；不能把旧 checkpoint 接续成功当作内容消费成立。
- 独立工程第 1 轮发现 IFT-001／002 两个 High：报告缺少冻结题／修订校验、partial 恢复可能改变分批；
  另发现 null 差异漏报与未确认消费输入的接续缺口。四项均窄修，详见[独立测试记录](2026-10-28-v5-codex-p0-independent-functional-test.md)。
  第 2 轮 **47 PASS**、Ruff 与格式通过；工程通过不代替语义验收。
- `acceptance-live-001` 的“5/5 PASS”漏了一道冻结题；`002` 的“0/6 REVISE”虽结构完整，但实际没有调用已获准的材料工具。
  两份原报告均保留且不作为有效语义结论；不能据 `002` 推导模型质量失败。
  实际出站清单证明工具存在，独立侧的“没有材料工具”自述不能作为根因事实。首阻塞归 `collaboration/routing` 的 prompt-contract。
  权威提示现明确 `read_material(material_id=...)`，发布前程序核对实际成功读取、题集完整唯一索引及目标修订，错误可反馈给原独立上下文修正。
  `003` 实际读齐三份输入，平台一次超时后自行重试，最终 6/6 PASS；未修订生产模型来迎合私有题。
- 新平台读取桥固定 Host 授权的 Project/Ontology，保留实际查询结果，并拒绝冻结修订漂移。
  该检查只保护目标身份，不判断业务语义。未知与缺测不补零。

新增入口见 [v5 README](../../../modeling_team/v5/README.md)。本批开发 `developer-round6.xml` 为 **47 PASS**；
真实 PostgreSQL／SDK 测试无跳过，保留 1 条已知第三方 Pydantic 警告。
后续只对新增脚本读取守卫与收尾做独立聚焦复查，复用未变的 47 项结果。
独立第 3 轮的 11 个读取守卫正反例、发布位置、最终脚本格式及 5 个 scope 收尾核对均 PASS。
最终 Ruff check、23 份 Python 文件格式、72 包锁文件、5 份文档的 76 个本地链接／19 个锚点检查通过。
GitNexus 索引仍滞后，只映射出无关 README 符号，未覆盖本批新包；本批影响范围依据实际导入、调用点、
diff 和上述测试核对，不宣称图影响覆盖。无关 GraphRAG 改动保持未暂存。

### 耗时、用量和下一步

截至 **2026-10-28 08:54:05 UTC**，从本任务首次执行授权起墙钟 **5 小时 47 分 57 秒**，含用户等待。
已记录 35 个 native turn 活动、无缺失 end；native 活动区间合并约 **16 分 20 秒**，不等于完整语义建模有效时间。
本轮主要为底座、接入、失败恢复、工程复测及文档工作，不把这些时间当作语义收益。
后续应直接复用本批成果进入 P1 小业务闭环，不继续扩展 P0 harness。

原始快照按 native thread 去重，已知输入 **255,842**、输出 **18,181**，合计 **274,023 token**：
建模／工程探针角色输入 123,728、输出 11,926；独立评价角色输入 132,114、输出 6,255。
缓存输入为输入子集，推理输出为输出子集，不重复相加。覆盖仍为 **PARTIAL**：
失败 SSE 响应可能未报告用量，平台内部排序／embedding 辅助调用和外部工程 Agent 未并入此观察。
外部 Host 单列 unknown，不计任务金额；不据这些数字生成新的费用总账或净降耗结论。
来源：`workspaces/v5-codex-p0/current-observation-summary.json` 及各原始 `usage.jsonl`／`activity.jsonl`。

Codex 暂定方案的主要功能风险已有实证；本批不切新任务默认入口，不宣称完整 P0 计量或 P1—P4 已交付。
按用户“遇到需要知晓或决策事项暂停”的要求，在这一选型结论处交接并暂停；当前没有新的收费授权请求。
下一步是 P1 最小业务工作空间／执行图与可复用应用接入，完整统计按用户允许的 v5 重实现边界继续收口。
