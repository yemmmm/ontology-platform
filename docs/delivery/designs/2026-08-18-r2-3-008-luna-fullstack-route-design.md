# R2.3-008 Luna 全栈路由/终态验证设计（复用 R2.3-005 切片）

- 状态：design-draft / plan review pending——功能合同已经用户确认（2026-08-17/18），设计与实施未开始
- Requirement：`docs/requirements/requirements-v2.3.md#r23-008-luna-全栈路由终态验证复用-r235-切片`
- Test plan：`docs/delivery/test-plans/2026-08-18-r2-3-008-luna-fullstack-route-test-plan.md`
- Delivery record：待实施开始后创建
- 复用基线：R2.3-007（`docs/delivery/designs/2026-08-17-r2-3-007-model-provider-routing-design.md`，含 §12 Luna Codex
  订阅认证）与 R2.3-005 formal 建模/验收流程

## 1. 目标

为已交付的 Luna 订阅路由提供一个可合法消耗建模 start 的 formal 载体，并用一次真实六角色运行实证
全栈 Luna 路由与终态：

1. 新建 formal run contract `R2.3-008`（scope mode=create，fresh Project/Ontology），复用
   `r2-3-005-modeling-team` 六角色语义与 R2.3-005 的 Dify C→B→A 业务切片源材料、建模与验收流程语义；
2. contract 默认 model profile 为 `openai-luna-medium`（六角色 `openai-codex/gpt-5.6-luna/medium`，
   Codex ChatGPT 订阅认证，沿用 R2.3-007 已交付合同，零改动）；
3. 完成门槛为路由/终态级：六个 package（含两个 fresh Examiner child）全部经 Luna 真实启动、Team Transport
   通信、平台/MCP 工具调用、typed 终态报告与完整 cleanup；evidence 记录逐角色 route binding 与
   `auth_mode=chatgpt-subscription`；
4. 新建 R2.3-008 专属 StartLedger（append-only，治理规则同现有 formal 账本），首批用户授权 3 个
   semantic start。

## 2. 已冻结功能合同（用户确认，不再重开）

1. scope mode=create（fresh Project/Ontology），平台自建资源，不绑定任何 caller-supplied 或 prior-run 资产。
2. 默认 model profile = `openai-luna-medium`；订阅 preflight、auth staging/barrier、TOML 投影沿用 R2.3-007
   已交付合同，本需求不修改其代码。
3. 验收门槛为路由/终态级；N-CQ 建模质量 usable-PASS verdict 不是完成门——质量证据自然产生并保留，但不阻塞
   本需求完成判定。失败按既有分类记 terminal，不自动 fallback 到 DeepSeek/API Key。
4. R2.3-008 专属 StartLedger，首批授权 3 个 semantic start，append-only 治理规则与现有 formal 账本一致。

## 3. 非目标

- 不产出 Luna 与 DeepSeek 的建模质量 A/B 结论（后续需求另行设计）。
- 不修改 R2.3-007 已交付的路由/认证/清理代码，除非执行中发现缺陷并按缺陷流程修复。
- 不改变六角色语义、权限、终态合同、Acceptance verdict schema 或 StartLedger 治理规则。
- 不新增 Provider、不引入运行中热切换或 fallback、不修改 `modeling_team/model-profiles/openai-luna-medium.yaml`
  及 closed catalog。
- 不在本轮实现 runner/acceptance 层面的"路由级 acceptance 模式"（见 §5.3 的机制结论与未来产品化分离）。

## 4. 载体缺口（为什么需要新合同）

R2.3-007 的 A6 probe 实证了单 turn 订阅路由，但完整 formal 六角色 Luna 运行尚未发生，且现有 formal 账本均
不可用：R2.3-005 账本随 start75 成功终态按"首个完整结果即终局"封闭（start76 reservation 已被
`previous semantic start lacks a terminal failure` 拒绝，零账本写入）；R2.3-003 账本绑定已验收的保留本体增量
序列；R2.3-002 账本上一 start 无 terminal_failure；非正式任务按 B3 合同不能选择 model profile。因此需要一个
新的 requirement-owned formal contract 作为合法消耗建模 start 的载体。

## 5. 新增表面

本需求是对已验证机械的薄增量：不新增运行时层次，只新增 requirement-owned 身份、资产与账本条目。

### 5.1 FormalRunContract

`modeling_team/formal_runs.py` 新增第三个 closed contract，并加入 `FORMAL_RUN_CONTRACTS`：

```python
R2_3_008_CONTRACT = FormalRunContract(
    requirement_id="R2.3-008",
    contract_id="r2-3-008-luna-route-create",
    profile_id="r2-3-008-modeling-team",
    task_id="r2-3-008-formal-acceptance",
    scope_mode="create",
    default_model_profile_id="openai-luna-medium",
    acceptance_standard_path="modeling_team/references/r2-3-008-acceptance-standard.json",
    ledger_requirement_id="R2.3-008",
)
```

- `deletion_policy` 保持 `None`：`validate_formal_run_contract_assets` 把 deletion policy 限定在 R2.3-003，
  create 合同不携带。
- `formal_run_contract_for` 的精确 `(profile_id, task_id)` 匹配、authoritative path 校验、profile 参数绑定
  （`formal_contract`/`acceptance_standard`）、model profile 文件存在性检查全部沿用现有通用逻辑，不需要
  R2.3-008 专用分支。
- 现有 `R2_3_005_CONTRACT`、`R2_3_003_CONTRACT` 字节不变。

### 5.2 六角色 Profile 与 Task YAML

`load_formal_run_configuration` 强制 profile 参数 `formal_contract == contract.contract_id` 且
`acceptance_standard == contract.acceptance_standard_path`，因此 R2.3-008 不能字节复用
`r2-3-005-modeling-team.yaml`。新增两个文件，均为 R2.3-005 对应资产的逐字镜像加最小重绑定（与 R2.3-003
拥有自己 profile 文件的做法一致）：

- `modeling_team/profiles/r2-3-008-modeling-team.yaml`：agents/communication 与 r2-3-005 完全一致；parameters
  仅改两个绑定——`formal_contract: r2-3-008-luna-route-create`、
  `acceptance_standard: modeling_team/references/r2-3-008-acceptance-standard.json`；`child_kinds`、
  `generic_multi_agent`、`candidate_progress_timeout_seconds` 原样保留。
- `modeling_team/tasks/r2-3-008-formal-acceptance.yaml`：schema_version 2；`role_sources`、`protocol_tools`、
  `expected_terminal_evidence`、`retain_nonempty`、`semantic_start_evidence` 与 r2-3-005 任务一致，唯一内容
  差异是 acceptance 角色的 role_source 指向新的 standard JSON 路径；objective 见 §5.3。

文件名必须精确匹配 contract ID 推导的 authoritative path（`modeling_team/profiles/<profile_id>.yaml`、
`modeling_team/tasks/<task_id>.yaml`），无需 R2.3-003 式特例。

### 5.3 验收标准 JSON 与路由/终态完成门机制

**机制研究结论（决定本节形态）。** 逐层核对当前消费方后，runner 的 acceptance 机械不存在、也无法通过
task objective / standard JSON 的措辞改写出一个"路由级"运行内完成门：

- `runner.py::_acceptance_ticket_policy` 要求 standard 声明至少一个 `competency_questions` 条目（精确键集
  `{id, question, approved_source_paths}`），create 合同的 `unknown_policy` 必须是
  `preserve-explicit-unknown`；
- `runner.py::_task_text` 对非 R2.3-003 formal 合同硬编码注入 Acceptance 指令文本"exactly two terminal
  Examiner reports per round"与"final cq-002 usable PASS"——standard 必须恰好声明 `cq-001`/`cq-002` 两个
  CQ ID，否则 Runner 投影的角色指令与实际 standard 不一致；
- `acceptance.py::_settlement_prerequisites_ready` + `settle()` 要求同一 state epoch 内每个 standard-owned
  CQ 都有 usable PASS verdict 才允许 settlement；`runner.py` 的 formal settlement 与 cleanup abort 路径、
  `__main__.py::_terminal_report_complete`（未达终态即记 `collaboration/routing` terminal failure）都建立其上。

把这套机械改成路由级门需要修改 `runner.py`/`acceptance.py` 的 delivered 行为，超出本需求允许的产品代码表面，
也违反"复用最近已验收基线"的优先级。因此采用**双层门**：

1. **运行内（不变）**：R2.3-008 run 完整执行 R2.3-005 质量流程——objective 与 2-CQ standard 全强度生效，
   候选应用、validation/reasoning、governed retrieval、两轮 CQ verdict 照常发生。这保证质量证据真实产生并
   保留，也避免向建模角色泄露"质量不阻塞完成"而污染质量证据。
2. **需求完成门（路由/终态级）**：R2.3-008 的完成判定由独立评审对照保留证据做出（项目规则：final semantic
   acceptance 独立于产生 live evidence 的过程）。run 级结局——settled（全部 CQ usable PASS）或未 settled
   （CLI 记 retryable `collaboration/routing` terminal failure）——都不单独决定 R2.3-008 完成：质量 verdict
   为 FAIL/BLOCKED 的 run 只要路由/终态证据完整即满足本需求；反之 settled 但路由证据不完整的 run 不满足。

**Task objective 措辞**：逐字镜像 `r2-3-005-formal-acceptance.yaml` 的 objective，仅把自引用
"For formal R2.3-005, …"改为"For formal R2.3-008 (reusing the R2.3-005 slice contract), …"。objective 刻意
**不**写入任何路由/终态门或"质量不阻塞"的表述——那是需求/设计/测试计划层的完成判据，进入角色指令会削弱
质量证据的可信度。

**验收标准 JSON**：`modeling_team/references/r2-3-008-acceptance-standard.json` 是 R2.3-005 质量标准的镜像
（同 2 CQ、同 approved_source_paths、同 checks/child_policy），仅改 `schema_version` 与 `requirement_ref`。
精确内容示例：

```json
{
  "schema_version": "r2-3-008-acceptance-standard/v1",
  "requirement_ref": "docs/requirements/requirements-v2.3.md#R2.3-008",
  "checks": [
    "source_fidelity", "scope", "ontology_structure", "explicit_unknowns",
    "validation_reasoning", "governed_retrieval", "evidence_lineage", "competency_questions"
  ],
  "unknown_policy": "preserve-explicit-unknown",
  "verdicts": ["PASS", "FAIL", "BLOCKED"],
  "competency_questions": [
    {
      "id": "cq-001",
      "question": "在 B 调用 C 作为 Tool 的关系中，当前能够确认的最新发布版本是什么，B 消费的是哪个输出？",
      "approved_source_paths": [
        "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/official/tools.mdx",
        "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/release-register.md",
        "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/workflow-landscape.md"
      ]
    },
    {
      "id": "cq-002",
      "question": "当 C 因 classifier dependency 不可用而没有返回 numeric score 时，B 会采取什么处理动作？",
      "approved_source_paths": [
        "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/exception-handling.md"
      ]
    }
  ],
  "failure_layers": ["modeling-quality", "interview", "protocol-delivery", "platform", "runtime"],
  "blocked_reasons": ["acceptance-evidence", "acceptance-input", "runtime-infrastructure", "source-missing", "state-invalidated"],
  "question_policy": "two-sequential-cqs-same-final-model-state",
  "child_policy": {
    "source": "approved-source-only",
    "platform": "ticket-scoped-read-only",
    "retry_attempts": [0, 1],
    "second_infrastructure_failure": "BLOCKED/runtime-infrastructure"
  }
}
```

CQ 内容与 R2.3-005 相同是有意决策：本需求的变量只有 model route，问题集保持不变使质量证据可与历史基线对照，
也满足 runner 注入文本对 2-CQ/cq-001/cq-002 的硬编码假设。

**已知重用痕迹（接受，不改）**：非 R2.3-003 合同的 runner 注入指令把 formal gate 标注为"R2.3-005"
（`runner.py` `formal_requirement_label`），且 verdict `schema_version` 硬编码为
`r2-3-005-acceptance-verdict/v1`。R2.3-008 run 中这些标签指被复用的 R2.3-005 门语义，属外观性痕迹；为避免
改动 delivered runner 文本机械而保留。

### 5.4 StartLedger 配置

`modeling_team/start_ledger.py` 新增 requirement-owned 配置（镜像 formal 政策）：

```python
_R2_3_008_REQUIREMENT_ID = "R2.3-008"
_R2_3_008_LEDGER_FILENAME = ".r2-3-008-start-ledger.jsonl"
_R2_3_008_LOCK_FILENAME = ".r2-3-008-start-ledger.lock"
# First user authorization (2026-08-17/18): 3 semantic starts for the Luna
# full-stack route verification carrier.  Encoded as the initial cap exactly
# like R2.3-005's single-start cap; see design §5.5.
_R2_3_008_INITIAL_START_CAP = 3
_R2_3_008_ADDITIONAL_STARTS = 3
```

`_LEDGER_CONFIGS` 新增条目，flags 与 R2.3-005 完全一致：`strict_sequence=True`、
`allow_incomplete_modeling_quality_repair=True`、`allow_variable_authorization=True`。由此获得的治理不变量与
现有 formal 账本相同：strict replay、reservation/semantic_start/terminal_failure 状态机、20 分钟
freeze-to-start 门、terminal failure 必须分类最新 start、授权不可重放/不可变、预算耗尽 fail closed。

**为什么首批授权不能以 `budget_authorization` 作为首条账本事件**：strict 账本上 `authorize_budget` 要求
`semantic_start_count == cap` 且前一条记录是最新 start 的 eligible terminal failure
（`_validate_strict_budget_predecessor`），空账本上必然失败；`initial_authorization` 事件被
`start_ledger.py` 硬性限定为 R2.3-003-only。因此在镜像 formal 政策的前提下，首批 3-start 授权只能沿用
R2.3-005 先例：以 requirement-owned 的 `initial_start_cap=3` 编码，账本首条事件即第一次 reservation。被否决的
替代方案：(a) 关闭 `strict_sequence` 使 `budget_authorization` 可开账——会丢失 strict replay/terminal
evidence/latest-start 分类等 formal 治理规则，违反"治理规则同现有 formal 账本"；(b) 把 `initial_authorization`
扩展到 R2.3-008——修改 R2.3-003 拥有的 delivered 账本语义，超出本需求允许表面。`authorize-budget` CLI 对
R2.3-008 仍然可用，但仅用于某次 terminal failure 之后的新一批用户授权扩展。

### 5.5 首批授权的记录

3-start 授权的溯源链为：requirement §已确认目标第 4 条（用户 2026-08-17/18 确认）→ `start_ledger.py` 配置
常量及其注释 → 本设计 §5.4 → delivery record 时间线中的授权冻结条目（见 §6）。账本文件本身首条事件为
reservation，不包含独立授权事件——与 R2.3-005 账本（initial cap 1、无开账事件）先例一致。

## 6. 真实运行的执行与授权冻结规则

首次真实 Luna formal run 前必须在 delivery record 冻结以下内容，然后才允许 reservation：

1. **授权冻结**：授权来源（用户对 R2.3-008 首批 3 个 semantic start 的确认）、预算（R2.3-008 账本 3 个
   semantic start，不追加新授权）、run identity 约定（如 `r23008-luna-<date>-start<N>`）、目标 model profile
   `openai-luna-medium`、失败即按既有分类记 terminal、不自动 fallback 到 DeepSeek/API Key/另一 effort。
2. **资产冻结**：delivery baseline commit、工作树 clean、profile/task/standard/model-profile 的 sha256、
   Host `codex login status` 为 ChatGPT（preflight 会复查）。
3. **freeze-to-start 门**：baseline freeze 时间戳到 ledger reservation 不超过现有 20 分钟上限；同一时刻最多
   一个 active reservation。
4. **运行纪律**：每个 start 的 run root 与证据完整保留；失败按四层分类（`modeling-quality`/
   `platform-contract`/`collaboration/routing`/`runtime/infrastructure`）记 terminal；不在未分类失败前预约下一
   start；剩余预算仅在 terminal failure 之后经明确继续决策消耗；run 中途不换 model profile。
5. **Cleanup owner**：Delivery Agent（主代理）——canonical gate 临时 admin key 运行结束即 revoke、核对 run root
   终态与零残留、不读取或记录 `auth.json`/token 内容。
6. **完成判定独立性**：路由/终态完成门由独立评审对照保留证据做出，评审过程不得创建或延续被评估的 run、
   不得改动保留证据。

## 7. Evidence 预期

真实 run 的保留证据须足以支撑路由/终态完成门，全部来自已交付机械的既有输出，不新增 evidence 面：

- baseline：`team_model_profile` 六角色 binding（`openai-codex/gpt-5.6-luna`、requested/effective
  `medium/medium`）、profile path/digest、`codex_subscription_auth_mode=chatgpt-subscription`、ledger
  identity（`.r2-3-008-start-ledger.jsonl` / `R2.3-008`）；
- 角色与子进程启动：四个 persistent role 与两类 fresh Examiner child（按 canonical package ID
  `source-examiner`/`platform-examiner`）的精确 route binding 与 `auth_mode=chatgpt-subscription`；
- 通信与工具：Team Transport delivery/coordination/report 事件、Protocol 的平台/MCP 工具 receipts（build
  session/batch、dry-run/apply、validation/reasoning、governed retrieval）、Examiner capability 调用；
- 终态：child `terminal_report_digest`、persistent role `report_task_result`、run 状态机记录（settled 或
  typed terminal failure 及其分类）；
- 清理：aggregate/per-role cleanup audit（scan complete、zero match、zero error、zero child residue）、
  listener/thread/socket 零残留、auth staging barrier 观察与移除、run root/日志零 secret；
- 账本：每次 start 的 reservation + semantic_start（+ 失败时 terminal_failure）记录在 R2.3-008 账本；
- 质量证据（CQ verdict、candidate receipts、validation/reasoning/retrieval receipts）：照常产生并保留，标注为
  非完成门。

## 8. 错误与失败分类

不新增 reason code，全部复用 R2.3-007/R2.3-005 已交付语义：

- 订阅认证预检失败：`codex-subscription-auth-unavailable` / `codex-subscription-auth-mode-mismatch`
  （typed `runtime/infrastructure`，发生在 reservation/run root/Agent start 前，不产生伪 evidence）；
- 运行期 entitlement/限额/网络/terminal 失败：`provider-upstream-failed`（latch 整个 run，aggregate cleanup，
  不 fallback）；
- 清理失败：`provider-session-cleanup-failed`（保持 typed terminal，不覆盖更早 failure）；
- 质量层：Acceptance FAIL/BLOCKED verdict 照常产生质量证据；run 若因未达 settlement 终止，CLI 记 retryable
  `collaboration/routing`——该分类只影响账本继续语义，不影响 R2.3-008 路由/终态完成判定；
- 账本层：预算耗尽、重复授权、非最新 start 分类等沿用现有 `TeamConfigurationError` 语义。

## 9. 最小实现面

- `modeling_team/formal_runs.py`：新增 `R2_3_008_CONTRACT`、注册表条目、`__all__` 导出。
- `modeling_team/start_ledger.py`：新增 R2.3-008 常量、`_LEDGER_CONFIGS` 条目、导出 requirement ID。
- 新增 `modeling_team/profiles/r2-3-008-modeling-team.yaml`、
  `modeling_team/tasks/r2-3-008-formal-acceptance.yaml`、
  `modeling_team/references/r2-3-008-acceptance-standard.json`。
- 新增 focused deterministic tests（合同解析、账本门、任务/standard 校验、默认 profile 投影、005/003 回归），
  放在 `modeling_team/tests/` 现有套件风格下。
- 不修改：`runner.py`、`acceptance.py`、`acceptance_runtime.py`、`runtimes/codex.py`、`model_routing.py`、
  transport/capability MCP、Team package instructions、`openai-luna-medium.yaml`、closed catalog、R2.3-007 任何
  delivered 行为、`backend/`、`frontend/`。

## 10. 验收条件

1. `validate`/`baseline`/`run` 以新 profile/task 对解析出 `R2_3_008_CONTRACT`；省略 `--model-profile` 时六角色
   投影为 `openai-codex/gpt-5.6-luna/medium`，digest 冻结一致。
2. R2.3-008 账本以 formal 政策镜像解析；3-start 初始预算、freeze 门、状态机与授权不可变性按现有规则行为；
   `initial_authorization` 对 R2.3-008 拒绝。
3. 真实 run 中六个 package（4 persistent + 2 fresh Examiner child）全部经 Luna 启动：证据含逐角色 exact
   binding 与 `auth_mode=chatgpt-subscription`，Examiner 按 canonical package ID 区分。
4. Team Transport 通信、平台/MCP 工具调用、typed 终态报告均有保留证据。
5. 完整 cleanup：零 listener/thread/socket/secret/child 残留，auth staging barrier 在首个 turn 后、任何
   ServerRequest/tool/MCP dispatch 前移除，run root/日志零 token/账户信息。
6. 账本只记录实际消耗的 start；失败分类符合四层 taxonomy；无 fallback、无未授权追加 start。
7. 质量证据（CQ verdict 等）已产生并保留，且完成判定不依赖其 PASS 与否。
8. R2.3-005/R2.3-003 合同字段与账本文件、历史 run/ledger evidence 字节不变；全量 `modeling_team`
   deterministic suite、compile/lint/diff checks 通过。

## 11. 当前最小范围与未来产品化

**当前最小范围**：§5/§9 所列表面 + focused tests + 一次有界真实 Luna formal run（3-start 预算、授权冻结、
证据检查、cleanup 审计）。

**未来产品化（明确不在本轮完成门内）**：

- Luna 与 DeepSeek 的建模质量 A/B 评测需求（需要独立的切片设计、判定标准与预算）。
- runner/acceptance 层面的"路由级 acceptance 模式"（若未来某需求需要运行内路由门而非需求级完成门，须显式
  扩展 acceptance standard schema 与 settlement 前置条件，另立需求评审）。
- 账本首批授权事件的一般化（requirement-owned initial authorization event 通用化、多账本管理 UI、自动
  post-failure 续跑编排）。
- 订阅额度观测、账号切换、余量预测等运营能力（R2.3-007 §12.7 已排除）。

## 12. 发布影响

- 变更仅限 `modeling_team/`（无 `backend/`/`frontend/` 改动），不触发 `ontology-platform.service` 重启门；
  独立测试轮可做被动 health 抽查（8001/5173）。
- 操作命令面：新载体通过 `--profile modeling_team/profiles/r2-3-008-modeling-team.yaml --task
  modeling_team/tasks/r2-3-008-formal-acceptance.yaml` 使用；`--model-profile` 可省略（contract 默认
  `openai-luna-medium`）。既有 R2.3-005/R2.3-003 操作命令与行为不变。
- 历史 run root、ledger record 与证据保持原字节；新账本文件由首次 reservation 创建于
  `workspaces/modeling-runs/`。
- Requirement 状态按 Draft → Design-reviewed → implemented → delivered 流转，与设计/测试计划/交付记录同步。
