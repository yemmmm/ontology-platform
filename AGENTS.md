# Repository Guidelines

项目名称为 **OntoWeave**（织义），原名 Ontology Platform。当前产品展示与说明使用新名称；
`ontology-platform`／`ontology_platform` 仍是现有部署、存储及 Agent 配置的兼容技术标识。
历史证据不因更名改写。名称范围见 [README](README.md#project-name)。

## 建模优先、平台防御与失败恢复规则

本节是建模流程优先级、平台校验和失败处理的统一规则。除非用户或适用的权威需求明确变更，
后续章节中的实验、实现和验收规则均不得与本节冲突。详细战术、案例和历史教训只作为参考，
不能扩大这里的完成门。

### 目标与启动优先级

- 当前阶段主要目标（2026-10-17用户确认）是降低 Delivery token 消耗，按
  [R4.3-030](docs/requirements/requirements-v4.3.md#r4-3-030)优先减少不必要的推理往返和
  累计上下文。真实建模与语义检索质量、完整业务范围、授权、交付正确性及独立验收是不可降低
  的约束；记录全任务成本转移，不以缓存率提高或局部字节减少代替真实降耗证据。平台流程与
  运行框架只做本目标必要的调整。当前实验必须有界，并与正在验收的阶段成比例；本节的
  `Priority L0` 表示最高运行优先级，与后文的 `L0 Runtime` 验收阶段不是同一概念。
- 优先复用最近已验收的需求、场景、代码、提示、角色配置、协议工具、fixture、证据读取方式和测试
  模式，只实现当前需求的必要差异。未经证明确实不兼容，不得重建已验证的执行路径；再次踩中已有
  记录的失败应视为流程缺陷。
- 用户授权真实建模后，除非用户明确允许更长准备期，必须在 20 分钟内开始第一次真实 semantic
  modeling start。启动前只做安全开始所必需的最小检查，不得前置全面审计、重复评审、mock run、
  smoke harness 或推测性验证。如果超时，停止扩展准备工作，报告耗时来源，缩短路径并进入真实建模。
- 历史或明确采用次数模式的授权默认包含三次建模轮次，除非用户明确指定其他数量或仅按
  fresh starts 计数。初建计一次；自查或验收后实际开始新的实质修模任务再计一次，同 run
  内修模也计数。同轮候选版本、分批写入、技术纠错和只读验收不重复计次；fresh production
  start／生产接续仍计一次，与该修模轮不双扣。轮次与 semantic-start 数分开记录，细则见
  [modeling-dev-loop](skills/modeling-dev-loop/SKILL.md#建模轮次计数与验收后修模)。
- 新授权只有在 Host／用户明确写入 `resource_authorization.mode=amount` 及稳定
  `budget_ref` 时才进入金额模式。金额模式不套用默认三轮或轮余额门；轮次与
  semantic-start 仍照实记录供分析，金额只约束资源消耗，不扩大业务目标、模型范围、写入
  安全或独立验收授权。预算创建、追加和价表只能由 Host／用户依据真实授权写入，Agent／
  Delivery 只能读取并沿授权执行。
- 授权额度是禁止未授权运行的边界，不是通过增加准备工作来保护的稀缺资产。次数模式额度用尽后
  必须停止新建模轮次并申请新授权；金额模式按预算状态暂停或恢复，不能把换 session／run
  当作清零。

### 校验层级与运行存活

- 只有直接保护以下结果的校验才可以成为硬门：源材料忠实度、业务范围、模型正确性、确定性
  dry-run/application、授权与受治理检索正确性，以及已经发生写入时的资源完整性。
- `fail-closed` 默认表示“不允许当前不安全或不完整的内容写入”，不表示“整个 run 永久死亡”。只要
  没有不确定写入或不可控污染，缺字段、格式错误、产物不完整、参数错误和可重试的协作问题都必须
  返回准确、可操作的反馈，并允许 Agent 修正后继续同一目标。
- Agent 数量、额外角色、具体协作顺序、尝试次数的代码内计数，以及其他不直接保护上述结果的流程
  偏好，不得成为不可恢复的平台硬拒绝。必要依赖可以排序，授权仍由用户控制，但平台不得把一种当前
  编排形态固化成所有建模的合法性条件。
- 平台应严格判断可观察的输入、写入和验收结果，不得替建模 Agent 决定业务语义、Ontology 拓扑或
  其他需要推理的建模选择。

### T0 — 阻断建模流程时的防御复核

当某条平台限制、校验或守卫导致 run 死锁、超时或不可修复时，在修补它暴露出的报错路径之前，
必须依次回答：

1. 这个防御功能是否必要，它保护的不变量在当前场景是否真实存在？
2. 它是否用不可恢复的硬拒绝防范了后果轻微、本可重试的情形？
3. 直接删除或降级该防御会产生什么具体后果？
4. 该后果是否可控，Agent 能否通过现有反馈通道自行修复？
5. 平台原子性、独立验收、证据记录、dry-run/apply 完整性等更高层机制是否已经覆盖同一风险？

若风险已被高层覆盖，或后果可控且可自修复，则优先删除该防御或降级为可恢复反馈，而不是修补
它的硬拒绝路径。只有删除会直接损害本节列出的硬门结果时，才保留并收窄该防御；保留时必须返回
类型化、可定位和可操作的错误。删除防御与修复报错二选一时，以“让建模流程可走通、让 Agent
能自我修复”为准则。

依据：R2.3-009 R8 三轮真实运行（start4/5/6，2026-08-20）的死因均为“不可恢复的硬拒绝叠加
无自修复通道”，而非建模质量问题。

### 失败归因、修复与继续

- 实时进度和终态失败必须可观察，并保留第一阻塞层。失败只归入 `modeling-quality`、
  `platform-contract`、`collaboration/routing` 或 `runtime/infrastructure`；不得用基础设施或平台失败
  推导模型质量结论，也不得用机械流程 PASS 代替真实语义 E2E PASS。
- 只修复真实证据指向的最窄失败层，然后恢复原始建模目标。若同一 run 可安全恢复，优先继续同一
  start；若必须创建 fresh start，则仍消耗用户授权额度，Agent 不得自行追加尝试。失败 workspace、
  原始事件和写入/清理证据必须保留，不得用后续成功覆盖。
- 若失败可由更清晰的 Task、角色、Skill、工具使用或交接说明预防，必须记录为 prompt-contract
  缺陷并修复权威提示面，然后才能开始下一次 semantic start。运行时指导可以解锁当前 run，但不能
  代替持久修复；平台或运行时缺陷也不得用提示文字掩盖。
- 修复窄失败时，不得顺带引入新的治理、Consumer、mutation、恢复、编排、审计或产品化机制。

### 验收与停止条件

- R4.3-024／025：当前模型 Batch 写入暂退独立 dry-run，Modeling 通过获准能力直接提交
  当前统一图及显式变更意图；程序填执行字段，在单次 apply 内校验并原子应用。下文历史
  dry-run 完成门在该路径改为 application 完整性；不再要求 Protocol 翻译审批或 dry-run
  成功证明。保留历史读取、授权、源忠实度、实际治理读回、必要恢复及独立语义验收。
  迁移／投影的 dry-run 和已应用模型的 preview 摘要不受影响；恢复模型 dry-run 须用户另定。

- R4.0-025：当前不要求 SHACL Shape、OWL 自动推理、专用规则注解／脚本或它们的回执。
  业务条件、计算口径、分类、显式关系和未知仍须忠实表达并受治理读取；基础写入校验、
  dry-run/apply、授权、原子性、实际读回、必要恢复及独立业务语义验收继续保留。

- 使用 `L0 Runtime`、`L1 Modeling quality`、`L2 Repeatability`、`L3 Productization` 分阶段验收，
  后一阶段不得成为前一阶段的前置条件。
- 模型最终接受仍必须具有 dry-run/application 完整性、源忠实度、有界业务范围、实际读回和受治理
  检索证据。最终语义验收必须独立于证据生产过程，不能创建、继续或修复被验收的 run，也不能修改
  保留证据。
- 分别记录语义建模与基础设施、harness、评审、文档所花的有效时间。如果语义建模不足一半，暂停
  扩展平台和 harness，报告原因并提出更短的通路；不得在真实语义证据缺失时继续增加控制机制。

## 工作方式与沟通

- 用户明确要求执行后，完成授权范围内的工作；常规、可逆的实现选择自行决定。只有答案会实质改变
  业务语义、范围、兼容性或授权边界时才提问，同时继续不依赖答案的工作。不要重复请求已有授权。
- 用户中途补充要求时保留原目标和已完成工作；先简短回答进度或概念问题，再继续任务。
- 默认用简洁中文，先结论后证据。复杂概念先用具体例子解释，再补必要术语；仅在用户要求教学式
  讲解时使用完整 `two-layer-explanation`，不为普通进度汇报强制生成术语表和检查题。
- 根据任务选用 skills，仅加载相关 references。用户指令优先于 skill 指南；若某条规则确实阻塞
  已授权工作，指出文件、原文和具体原因，区分硬要求与自己的推断。
- 需要并行工作或独立验收时按当前授权、需求和运行环境分工；交接目标、输入、输出、文件/资源归属
  和证据边界。不要仅为满足角色数量增加 Agent，也不要用自评代替要求的独立验收。

## 项目导航

FastAPI 后端位于 `backend/app/`：`api/` 为 HTTP 合同，`services/` 为工作流，`repositories/`
为 PostgreSQL/RDF 持久化，`domain/` 为领域模型，`mcp/tools/` 为 Agent 工具。
重点服务为 `modeling_batches.py` 与 `semantic_context_query.py`；迁移在 `backend/migrations/`。
React/Vite 前端在 `frontend/src/`；运行与建模诊断可从 `BuildContextDebugPage.tsx` 入手。

## Project Target Guidance

`docs/requirements/` contains the project's versioned authoritative requirement sources. Before
architecture, API, storage, semantic modeling, MCP, or UI work, identify the requirement and version
that own the current task, read that entry first, then follow its declared base and related-version
links where necessary. No older version file, including `requirements-v1.0.md`, is the default
global core for every task.

Treat differences between the current implementation and the applicable requirement set as
implementation gaps, not as reasons to silently redefine the target. Surface conflicts explicitly,
and update the owning requirement when the target or delivery decision changes.
`docs/reference/glossary.md` remains the reference for canonical terminology only; ADRs record
architectural decisions. Neither current code nor older planning documents override the applicable
versioned requirements.

## 工作流与按需读取

- 宿主推进建模使用 [modeling-dev-loop](skills/modeling-dev-loop/SKILL.md)；Team 内部技能集中在
  [modeling_team/skills/](modeling_team/skills/README.md)，Modeling 角色的方法为其中的 `ontology-modeling`。
  当前 Team 执行以选定的 `modeling_team/tasks/`、`profiles/` 和 `agent-packages/` 合同为准。
  Delivery Agent 负责版本与授权检查，隔离建模 Agent 只接收获准输入。不要把完整仓库、记忆
  或隐藏答案注入盲测。
- `.codex/`、`.claude/` 中标为 DEPRECATED 的旧 Harness、角色及 `ontology-builder` 仅为历史
  证据，不是当前 Team Runner，也不是启动依赖。
- 建模与平台防御遵循上方统一规则。仅在具体失败需要历史经验时读取
  [实验经验](docs/reference/modeling-agent-experiment-lessons.md)，不把经验扩成完成门。
- Delivery Agent 负责确定性执行、资源生命周期、清理和证据交接；脚本只是工具，不是语义裁判。
  本地实验优先复用现有工具和 gitignored 可读目录。不创建只匹配本次阶段输出的一次性验收器；
  可复用平台合同的确定性验证不受此限制。
- 明确区分当前最小范围与未来产品化；安全细分、跨机器协调、自动恢复、审计框架和管理 UI
  只有在直接保护当前建模、检索或已写入资源完整性时才纳入本次范围。

## Platform and Reference-Ontology Boundary

Treat concepts that appear in a customer ontology, evaluation corpus, or reference scenario as
ontology data by default, not as platform product concepts. Dify Workflow, Input, Node, Output,
`hasNode`, and `node_order` are examples of business semantics that must remain in the modeled
ontology unless an authoritative requirement and architectural decision explicitly promote a
concept into the platform domain.

- Do not add domain-specific routes, read models, schemas, fields, branches, or sorting rules merely
  to answer one reference-ontology question.
- When several business scenarios need easier consumption, improve generic semantic capabilities:
  authorized scope, related-expression retrieval, resource-kind filters, fused context,
  fact/relation expansion, field projection, Evidence/lineage, pagination, and explicit
  completeness.
- The platform returns modeled resources, predicates, values, topology, provenance, and state. The
  consuming Agent interprets those facts into domain-specific structures and natural-language
  answers; the platform must not silently assign business meaning or invent missing facts.
- Domain-specific names and expected values may appear in fixtures and acceptance assertions to
  prove generic behavior, but production code must remain usable for unrelated ontologies.
- If a requirement appears to promote a reference-ontology concept into platform behavior, stop
  before implementation, surface the boundary conflict, and correct or explicitly confirm the
  requirement first.

## Build, Test, and Development Commands

- `./scripts/start-local.sh`: starts/checks PostgreSQL and Oxigraph, syncs dependencies, runs migrations, and starts backend `8001` plus frontend preview `5173`.
- `cd backend && uv sync --extra dev`: installs backend runtime and development dependencies.
- `cd backend && uv run alembic upgrade head`: applies database migrations.
- `cd backend && uv run uvicorn app.main:app --reload`: runs the API at `http://localhost:8000`.
- `cd backend && uv run python -m app.mcp.server`: runs the MCP server.
- `cd frontend && npm install`: installs frontend dependencies.
- `cd frontend && npm run dev`: starts the Vite dev server.
- `cd frontend && npm run build`: type-checks and builds the frontend.
- `cd frontend && npx playwright test`: runs the browser smoke checks used for workspace verification.

## Coding Style & Naming Conventions

Backend code targets Python 3.11 and uses Ruff with a 100-character line length. Keep API handlers thin, put workflow logic in services, and keep storage details in repositories. Use `snake_case` for Python modules, functions, and variables; use `PascalCase` for Pydantic and domain classes.

Frontend code uses TypeScript, React, and ES modules. Use `PascalCase` for components, `camelCase` for functions and state, and keep styling in `frontend/src/styles.css` for now.

## Testing Guidelines

Use layered testing for requirement development across `backend/`, `frontend/`, and `modeling_team/`:

- **Development iterations:** run the requirement cases, reproduced failures, and directly related tests.
- **Delivery verification:** run regression tests for affected modules and critical calling paths based on
  the actual change. Preserve relevant authorization, idempotency, and real loading/runtime contract checks.
- **Full regression:** run the affected components' full suites once for shared-core code changes,
  unclear impact boundaries, or before code merge/release. Full regression is not a default requirement
  for every edit or ordinary local commit.

Reuse passing results while the relevant code, dependencies, configuration, and runtime environment
remain unchanged. Final edits must be covered by the appropriate tests; repeat or broaden checks only
for new changes, failures, or unresolved evidence gaps. Report the tested scope and limitations.
Full regression does not replace required independent semantic acceptance.

Backend dev dependencies include `pytest`; place tests under `backend/tests/` with names like
`test_metadata.py` or `test_graph_validation.py`. Prefer service-level tests for validation rules.
Behavior changes under `backend/` must include new or updated tests. Run
`cd backend && uv run pytest <test-paths>` for the affected scope; use `cd backend && uv run pytest`
when the full-regression conditions above apply. Do not report a backend change as complete while
required tests are failing.
If the test command cannot be run because an external dependency is unavailable, document the exact
blocker and the narrower checks that were run.

For UI changes, run `cd frontend && npm run build` and affected Playwright tests with
`cd frontend && npx playwright test <test-paths>`. Use `cd frontend && npx playwright test` when the
full-regression conditions above apply. Document any manual browser checks that were necessary.

Documentation-only and instruction-only changes require relevant link, format, and contract checks;
they do not require backend/frontend suites or a service restart. Run changed skill validators when
available. These checks do not establish model quality or real-runtime acceptance. After required
checks pass, repeat or broaden them only for new changes, failures, or unresolved evidence gaps.

## Runtime Restart Rules

The local application is managed by the `ontology-platform.service` user systemd unit. After
changing code under `backend/` or `frontend/`, complete the required tests above and then restart
the service with `systemctl --user restart ontology-platform.service`. Changes that affect both
sides, shared runtime configuration, dependencies, migrations, or `scripts/start-local.sh` also
require the same restart.

After every restart, wait for the unit to become active and verify the affected runtime endpoints.
Use `systemctl --user --no-pager --full status ontology-platform.service`, check the backend with
`curl --fail http://127.0.0.1:8001/api/health`, and check the frontend with
`curl --fail http://127.0.0.1:5173/`. Do not report a frontend or backend change as complete until
the restarted service and the affected endpoint are healthy. If restart or verification fails,
inspect `journalctl --user -u ontology-platform.service` and report the exact blocker.

## Commit & Pull Request Guidelines

Recent commits use short imperative summaries, for example `Add local startup workflow`. Keep commit subjects concise and action-oriented.

Pull requests should include a clear description, relevant issue links, migration notes for schema changes, and screenshots or recordings for visible UI changes. Mention the commands you ran.

## Security & Configuration Tips

Copy `.env.example` to `backend/.env` for local development. Do not commit real credentials, API keys, database dumps, `backend/.venv/`, `frontend/node_modules/`, or generated `frontend/dist/` artifacts unless explicitly required.

## Relational Semantic-Layer Guidance

These principles apply to any relational business-scenario modeling work:

- Keep business rows in the relational source. The RDF/ontology semantic layer describes business meaning,
  relationships, metrics, policies, and mappings; it must not be populated with source-table row instances merely
  to make SQL question answering work.
- Treat database schema (table names, columns, keys, constraints, and sample values) as mapping evidence, not as
  business truth. Confirm terminology, lifecycle, causality, metric definitions, and unknowns through the business
  interview before asserting them as semantics.
- Model a complete scenario as logical slices and preserve a project-level view of shared terms, dependencies,
  mappings, and cross-slice questions. A logical slice does not imply one Ontology; do not preselect one or many
  Ontologies from table count alone.
- A Consumer Agent must obtain an authorized semantic context before generating SQL. NL2SQL may be used only after
  the semantic concepts, join paths, and metric rules in that context constrain and explain the generated query.
- Separate semantic-knowledge authorization from business-data authorization. A denied semantic read must use the
  platform's `forbidden` contract without leaking protected concepts or mappings, but that result does not secure
  rows or columns in a database reachable through another client.
- Keep the current external SQL execution adapter minimal: execute the supplied SQL and return rows or a database
  error. Do not add data authorization, policy rewriting, auditing, or connector-framework behavior to this adapter;
  production data authorization belongs to an external query gateway, business service, or database policy layer.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ontology-platform** (33731 symbols, 70200 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- Use `impact({target: "symbolName", direction: "upstream"})` before changes to call relationships, public interfaces, or cross-module behavior. Report the affected callers/processes and risk. Local changes with clear impact can use focused code and call-site inspection; documentation-only changes do not require symbol analysis.
- For code commits, use `detect_changes()` to check affected symbols and execution flows when GitNexus is available. Documentation-only commits need a diff and relevant link/format checks. For regression review against the default branch, use `detect_changes({scope: "compare", base_ref: "main"})` when applicable.
- If GitNexus is unavailable or stale, use focused call-site inspection, `git diff`, and relevant checks; disclose the limitation. Reindex only when needed to resolve a material impact question, rather than blocking every edit or commit on tooling.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar execution flows, use `query({search_query: "concept"})` when it helps. Use direct text/file search for known names, paths, and small local questions.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- For symbol renames, prefer semantic `rename`; if unavailable, inspect all references and verify the affected behavior before committing.
- Do not claim graph-based impact coverage when only diff or call-site inspection was performed.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/ontology-platform/context` | Codebase overview, check index freshness |
| `gitnexus://repo/ontology-platform/clusters` | All functional areas |
| `gitnexus://repo/ontology-platform/processes` | All execution flows |
| `gitnexus://repo/ontology-platform/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
