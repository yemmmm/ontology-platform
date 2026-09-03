# Repository Guidelines

## 建模优先、平台防御与失败恢复规则

本节是建模流程优先级、平台校验和失败处理的统一规则。除非用户或适用的权威需求明确变更，
后续章节中的实验、实现和验收规则均不得与本节冲突。详细战术、案例和历史教训只作为参考，
不能扩大这里的完成门。

### 目标与启动优先级

- 当前首要目标是获得真实的建模质量与语义检索质量证据。平台流程、运行框架和机械校验只为这个
  目标服务，不能成为独立的优化目标。当前实验必须有界，并与正在验收的阶段成比例；本节的
  `Priority L0` 表示最高运行优先级，与后文的 `L0 Runtime` 验收阶段不是同一概念。
- 优先复用最近已验收的需求、场景、代码、提示、角色配置、协议工具、fixture、证据读取方式和测试
  模式，只实现当前需求的必要差异。未经证明确实不兼容，不得重建已验证的执行路径；再次踩中已有
  记录的失败应视为流程缺陷。
- 用户授权真实建模后，除非用户明确允许更长准备期，必须在 20 分钟内开始第一次真实 semantic
  modeling start。启动前只做安全开始所必需的最小检查，不得前置全面审计、重复评审、mock run、
  smoke harness 或推测性验证。如果超时，停止扩展准备工作，报告耗时来源，缩短路径并进入真实建模。
- 每次授权默认包含三次 fresh semantic modeling starts，除非用户明确指定其他数量。授权额度是禁止
  未授权运行的边界，不是通过增加准备工作来保护的稀缺资产。Agent 负责记录轮次、run ID 和额度消耗；
  平台代码不得用建模次数硬门代替用户授权。当一次 start 能产生语义证据时应及时使用；额度用尽后
  必须停止并申请新授权。

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

- 使用 `L0 Runtime`、`L1 Modeling quality`、`L2 Repeatability`、`L3 Productization` 分阶段验收，
  后一阶段不得成为前一阶段的前置条件。
- 模型最终接受仍必须具有 dry-run/application 完整性、源忠实度、有界业务范围、验证/推理和受治理
  检索证据。最终语义验收必须独立于证据生产过程，不能创建、继续或修复被验收的 run，也不能修改
  保留证据。
- 分别记录语义建模与基础设施、harness、评审、文档所花的有效时间。如果语义建模不足一半，暂停
  扩展平台和 harness，报告原因并提出更短的通路；不得在真实语义证据缺失时继续增加控制机制。

## 用户咨询时的双层解释法

在进行较长时间的任务时，如果用户就某个概念、当前进度或方案向 Agent 咨询信息，Agent 应使用「双层解释法」（`two-layer-explanation` skill）回答：

1. **小白版**：用生活化语言和一个具体例子，让没有背景的人也能听懂；
2. **专业版**：使用准确术语，讲清核心机制、适用边界和常见误解；
3. **收尾整理**：列出小白说法与专业术语的对应关系、用户最容易理解错的地方，以及 1 个用于检查是否真正理解的问题。

## Project Structure & Module Organization

This repository contains a FastAPI backend and a Vite/React frontend for an ontology and knowledge graph platform. Key paths:

- `backend/app/api/`: HTTP routes, dependencies, and schemas.
- `backend/app/api/semantic.py`: semantic graph, query, validation, reasoning, and migration routes.
- `backend/app/api/build_sessions.py`: project Build Session, checkpoint, and lease routes.
- `backend/app/api/modeling_batches.py`: modeling batch dry-run, apply, query, and recovery routes.
- `backend/app/domain/`: ontology and graph domain models.
- `backend/app/repositories/`: PostgreSQL and RDF/Oxigraph persistence.
- `backend/app/services/`: validation and application workflows.
- `backend/app/services/modeling_batches.py`: external-Agent modeling application workflow.
- `backend/app/services/semantic_context_query.py`: structured Agent query pipeline.
- `backend/app/mcp/`: MCP server entrypoint.
- `backend/app/mcp/tools/`: current system, interview, build-session, modeling, evidence, and semantic tools.
- `backend/migrations/`: Alembic migrations.
- `frontend/src/`: React UI entrypoint and styles.
- `frontend/src/pages/BuildContextDebugPage.tsx`: read-only Build Session/modeling diagnostics.
- `docs/`: architecture, API, MCP, UI docs, and ADRs.

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

## Current Development Priority

The unified modeling and guardrail priorities are defined in
`建模优先、平台防御与失败恢复规则`. This section limits productization scope. Prefer the
simplest implementation and operating workflow that preserves or improves modeling and semantic
retrieval quality.

- Do not make productization concerns such as fine-grained security, generalized version
  management, immutable audit history, cross-machine coordination, automatic crash recovery,
  complex orchestration, or polished management UI prerequisites for a modeling-quality experiment.
- Design documents may reserve extension points and list those concerns as future capabilities, but
  current implementation and acceptance must not include them unless they are necessary to protect
  modeling correctness, retrieval correctness, or the integrity of an immediately applied model.
- For local Agent workflow experiments, prefer a repo-local, gitignored, human-readable shared
  directory and small deterministic scripts over new backend tables, APIs, services, or frameworks.
- Separate every new modeling-workflow design into `current minimal scope` and `future
  productization`. Do not silently promote future features into the current completion gate.
- Existing platform capabilities may be reused, but do not require every available governance,
  recovery, lineage, event, or audit mechanism in each local iteration merely because it exists.

## External Modeling Agent Experiment Rules

The rules in this section are mandatory unless the user or an authoritative requirement explicitly
changes them. Detailed tactics, examples, and historical lessons are reference-only in
`docs/reference/modeling-agent-experiment-lessons.md`; that document cannot override these rules.
The unified start priority, attempt authorization, guardrail hierarchy, failure recovery, and
acceptance boundaries are defined in `建模优先、平台防御与失败恢复规则`; do not restate or weaken
them here.

- The Delivery Agent owns deterministic execution, resource lifecycle, cleanup, and evidence
  handoff. A repo-local script is only its tool, not a Host layer, autonomous modeling role, or
  semantic acceptance authority.
- Do not create hard-coded programs that inspect one temporary requirement's or one stage's output
  merely to support that implementation run. Such one-off checkers are slow to build, brittle, and
  prone to validating the script's assumptions instead of the real result. Prefer direct evidence
  inspection and existing generic validators. This restriction does not apply to validation that
  protects a stable, reusable requirement or platform contract; temporary implementation scripts
  must remain small, disposable, and non-authoritative.
- Keep deterministic mechanics out of model reasoning. Tools own protocol formatting, stable
  identities, immutable publication, retries, and parsing; modeling Agents own business semantics,
  ontology structure, evidence, Shapes, relations, and explicit unknowns.
- Preserve requested parallel execution. Freeze contracts and assign non-overlapping ownership of
  files, ports, Project/Ontology IDs, runtime directories, shared records, and cleanup before work
  begins.

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

Backend dev dependencies include `pytest`; place tests under `backend/tests/` with names like `test_metadata.py` or `test_graph_validation.py`, then run `cd backend && uv run pytest`. Prefer service-level tests for validation rules.

Any change under `backend/` must include new or updated tests when behavior changes and must be
verified with `cd backend && uv run pytest` before the work is considered complete. v0.4 work
should keep coverage around semantic services, modeling application, relation metadata, lineage,
governance application, and import/export round-trips. Do not report a backend change as complete while tests are failing.
If the test command cannot be run because an external dependency is unavailable, document the exact
blocker and the narrower checks that were run.

For UI changes, run `cd frontend && npm run build` and `cd frontend && npx playwright test`, then
document any manual browser checks that were necessary.

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

This project is indexed by GitNexus as **ontology-platform** (27547 symbols, 57805 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

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
