# Repository Guidelines

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

The current project stage prioritizes **modeling quality and semantic retrieval quality**. Prefer
the simplest implementation and operating workflow that preserves or improves those two outcomes.

- Do not make productization concerns such as fine-grained security, generalized version
  management, immutable audit history, cross-machine coordination, automatic crash recovery,
  complex orchestration, or polished management UI prerequisites for a modeling-quality experiment.
- Design documents may reserve extension points and list those concerns as future capabilities, but
  current implementation and acceptance must not include them unless they are necessary to protect
  modeling correctness, retrieval correctness, or the integrity of an immediately applied model.
- For local Agent workflow experiments, prefer a repo-local, gitignored, human-readable shared
  directory and small deterministic scripts over new backend tables, APIs, services, or frameworks.
- Keep only the quality gates that directly protect source fidelity, business scope, model
  correctness, deterministic dry-run/application, and competency-question or retrieval acceptance.
- Separate every new modeling-workflow design into `current minimal scope` and `future
  productization`. Do not silently promote future features into the current completion gate.
- Existing platform capabilities may be reused, but do not require every available governance,
  recovery, lineage, event, or audit mechanism in each local iteration merely because it exists.

## External Modeling Agent Experiment Rules

The rules in this section are mandatory unless the user or an authoritative requirement explicitly
changes them. Detailed tactics, examples, and historical lessons are reference-only in
`docs/reference/modeling-agent-experiment-lessons.md`; that document cannot override these rules.

- Prioritize evidence about modeling and semantic retrieval quality. Keep the current experiment
  bounded, proportional to its acceptance stage, and separate from future productization.
- Start the first real modeling attempt within 20 minutes unless the user explicitly authorizes a
  longer preparation phase. If the gate is missed, stop, report the time consumers, and reduce the
  setup before continuing.
- Treat the user-authorized modeling-attempt budget as a hard boundary. Count only fresh semantic
  modeling starts, preserve every attempt, and request new authorization after exhaustion.
- Use staged acceptance: `L0 Runtime`, `L1 Modeling quality`, `L2 Repeatability`, and
  `L3 Productization`. Never make a later stage a prerequisite for an earlier one.
- Before implementation, inventory and reuse the closest accepted requirement, scenario, code,
  prompts, role configuration, protocol helpers, raw evidence readers, and tests. Extend them with
  the smallest necessary delta; document and review any proven incompatibility before replacement.
- The Delivery Agent owns deterministic execution, resource lifecycle, cleanup, and evidence
  handoff. A repo-local script is only its tool, not a Host layer, autonomous modeling role, or
  semantic acceptance authority.
- Keep deterministic mechanics out of model reasoning. Tools own protocol formatting, stable
  identities, immutable publication, retries, and parsing; modeling Agents own business semantics,
  ontology structure, evidence, Shapes, relations, and explicit unknowns.
- Require dry-run/application integrity, source fidelity, bounded scope, validation/reasoning, and
  governed retrieval evidence before accepting a model. Do not add unrelated governance,
  Consumer, mutation, recovery, or orchestration scope to repair a narrow failure.
- Make live progress and terminal failures observable, fail fast, and preserve the failing layer as
  `modeling-quality`, `platform-contract`, `collaboration/routing`, or
  `runtime/infrastructure`. Repair only the narrow layer and resume the original modeling goal.
- Preserve requested parallel execution. Freeze contracts and assign non-overlapping ownership of
  files, ports, Project/Ontology IDs, runtime directories, shared records, and cleanup before work
  begins.
- Final semantic acceptance must be independent from the process that produced the live evidence.
  Independent testing must not create or continue the run it evaluates and must not mutate retained
  evidence.
- Track time spent on semantic modeling versus infrastructure, harness, review, and documentation.
  If semantic modeling is less than half of active effort, pause and propose a smaller path before
  expanding the harness.

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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ontology-platform** (22155 symbols, 44608 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
