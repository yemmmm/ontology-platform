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

`docs/requirements/requirements-v1.0.md` is the authoritative global reference for the project's target state.
Read it before architecture, API, storage, semantic modeling, MCP, or UI work, and use its delivery
scope, priority, status, and acceptance criteria to guide designs, code, tests, and documentation.

Treat differences between the current implementation and this requirements list as implementation
gaps, not as reasons to silently redefine the target. Surface conflicts explicitly, and update the
requirements list when the target or delivery decision changes. `docs/reference/glossary.md` remains the
reference for canonical terminology only; ADRs record architectural decisions. Neither the current
code nor older planning documents override the requirements list.

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

When debugging or evaluating an external modeling Agent, optimize first for evidence about modeling
quality. Do not turn the initial experiment into delivery of a production-grade Agent Runtime,
security boundary, or generalized evaluation platform.

- Start the first real modeling attempt within 20 minutes unless the user explicitly authorizes a
  longer preparation phase. If no real attempt has started by then, stop preparation, report what
  is consuming time, and reduce the setup to the smallest executable path.
- Treat a limited modeling-attempt budget, including a three-attempt limit, as a checkpoint against
  repeatedly modeling in the wrong direction, not as a scarce resource that must be protected with
  broad pre-modeling tests. Do only the minimum L0 checks needed to start a real attempt; do not
  delay modeling with speculative runtime, infrastructure, mutation, repeatability, or acceptance
  testing merely to avoid consuming an attempt. The user expects early attempts to make the current
  direction observable and accepts that an attempt may be spent learning. When the budget is
  exhausted, stop, summarize the direction and evidence from the attempts, and ask the user to
  authorize more attempts instead of expanding preflight work.
- The initial completion gate should normally be one bounded corpus or scenario, one Agent, one
  fresh ontology scope, one deterministic dry-run/application path, validation, and one governed
  query. Independent consumers, mutation suites, repeated-success measurement, recovery matrices,
  and production security checks belong to later gates unless the user explicitly requests them or
  the first run proves they are necessary.
- Use staged acceptance:
  - `L0 Runtime`: the Agent can reach its model and required tools.
  - `L1 Modeling quality`: the Agent understands the source, finds consequential semantic gaps,
    models explicit unknowns, and passes validation/query checks.
  - `L2 Repeatability`: independent consumption, repeated runs, and mutation checks.
  - `L3 Productization`: strict isolation, credential brokering, recovery, immutable audit, and
    generalized orchestration.
  Do not make L2 or L3 prerequisites for L1.
- Before designing or implementing a requirement, inventory the closest previously accepted
  requirement, scenario, launcher, prompts, role configuration, protocol helpers, audit logic, and
  tests. Reuse those verified assets directly and extend them with the smallest necessary delta;
  do not rebuild an already validated execution path from scratch. If reuse is impossible, record
  the concrete incompatibility and evidence in the design and delivery record, preserve the old
  path as a regression oracle, and obtain plan review before introducing a replacement. New
  acceptance logic must compare against the prior raw evidence source and include a regression that
  would fail if the previously verified behavior were misread or dropped.
- The Delivery Agent owns Project/Ontology preparation, Build Session, lease, Modeling Batch,
  validation, reasoning, query, cleanup, and evidence handoff. Reuse one previously validated
  deterministic repo-local execution workflow as the Delivery Agent's tool; do not promote that
  script into a separate Host layer or autonomous acceptance role. A new Agent Runtime such as
  Codex or Pi should normally add only a thin adapter for launch, prompt/input assembly, tool
  bridging, event normalization, and terminal-state detection.
- Keep mechanical protocol work out of the model. Deterministic tools must own UUIDs, canonical
  JSON, filenames, atomic file publication, request schemas, lease refresh/retry, checkpoint
  bodies, and response parsing. The Agent should spend its reasoning on business semantics, Class,
  Property, Shape, relation, evidence, and explicit-unknown decisions.
- For a local modeling-quality experiment, prefer direct model-provider access with an ephemeral
  credential when that is the shortest safe path. Add a Host model proxy, network sandbox, or
  stronger credential isolation only when explicitly required or when a demonstrated risk makes it
  necessary.
- Make live failures observable and fail fast. Preserve the real failure category across adapters,
  expose progress milestones, bound first-response and terminal waits separately, and terminate
  promptly after a provider or Agent terminal error. Do not wait for a large global timeout when
  the underlying call has already failed.
- Keep design, review, documentation, and regression work proportional to the current gate. A
  modeling-quality smoke run must not be delayed by exhaustive negative matrices or full delivery
  ceremony unless platform code is changing or a concrete high-risk condition requires it.
- Parallel execution is an explicit user requirement and should be preserved. Run independent work
  in parallel with subagents when requested; do not treat parallelism itself as a failure cause.
  Before starting parallel tasks, freeze each task's contract and assign non-overlapping ownership
  of files, ports, Project/Ontology IDs, runtime directories, and cleanup responsibility. Shared
  requirements and delivery records need a designated writer or append-only coordination rule.
- Separate failures into `modeling-quality`, `platform-contract`, and `runtime/infrastructure`
  categories. A runtime or transport failure must not trigger additional ontology workflow,
  Consumer, mutation, or governance scope. First repair or bypass the narrow failing layer, then
  resume the original modeling goal.
- Track the time spent on actual semantic modeling versus infrastructure, harness, review, and
  documentation. If actual modeling is less than half of the active effort, pause and propose a
  smaller path before expanding the harness.

### Lessons from the R2.2 L3 modeling-team evaluation

Apply these rules to later multi-Agent modeling experiments. They summarize the failed attempts and
accepted recovery path from R2.2-001 L3:

- Treat raw Agent rollouts as the authority for collaboration evidence. An outer
  `codex exec --json` summary can omit child activity and must not be used to conclude that a
  coordinator failed to create a Modeling Agent. Prove the chain with the coordinator
  `spawn_agent` call, `agent_type`, `fork_turns`, matching `sub_agent_activity`, and the child
  `session_meta` parent/role fields. Reuse the already accepted L0/L1 reader and fixtures.
- Count only a fresh Coordinator/Modeling Agent team as a modeling start. A Protocol retry that
  reuses the same approved candidate, answers, coordinator, and Modeling Agent is not a new
  modeling opportunity. Every retry must still have an exact transcript, failure category,
  cleanup proof, and hash-bound receipt; never use this distinction to obtain another semantic
  modeling attempt.
- Preserve recovered question/answer sessions as an append-only state machine. Each question cycle
  must bind its canonical question hash, exact frozen answer, coordinator Session, originating
  resume transcript, previous cycle, and previous correction. Never recompute or overwrite an
  earlier correction after releasing a later answer, and test cross-cycle substitution and
  previous-link tampering.
- When a resumed Agent must publish files, put sandbox and working-directory options on the parent
  `codex exec` command before `resume`, and probe the real boundary: `/work` writable, `/opt`
  read-only, repository and tester-only paths absent. Do not assume an L1 resume command is writable
  enough for an L3 multi-question workflow.
- Reuse the previously verified interpreter runtime mount. Mounting the backend source parent can
  miss the virtual-environment interpreter and can expose `.env`; mount only the resolved runtime
  root and the explicitly required script files. A failed MCP startup before Agent creation must
  remain `runtime/infrastructure`, with credentials and owned resources still cleaned.
- Make credential lifecycle a Delivery-Agent responsibility. Perform the no-key authentication
  rejection before creating/injecting the temporary key, stage only a redacted proof, and tell the
  keyed Protocol Agent not to repeat the probe. Repeating the probe after injection can cancel an
  otherwise valid Build Session and is not modeling evidence.
- Dry-run must reject every value that would fail at the persistence sink. In particular, validate
  relation source, predicate, and target as absolute RDF IRIs before producing any RDF delta.
  Negative tests must prove zero workspace change, zero RDF delta, and no write fence; a dry-run
  that merely postpones an IRI error until atomic apply is a platform defect.
- Prefer bounded schema, entity, and relation Batches when relations require platform-issued IRIs.
  Apply entity Batches first, reread their absolute IRIs, then build relation Batches. The result
  contract must represent applied Batches as a non-empty list, and mechanical evidence checks must
  reread every listed Batch rather than assuming exactly one Batch.
- Use role-specific timeouts. Keep first-response and terminal waits separate; retain the normal
  coordinator/resume timeout, and extend only a Protocol execution that has demonstrated valid
  progress. A generic timeout must not turn a healthy long-running application into a false
  modeling failure.
- Keep evidence inspection genuinely read-only. Do not call a `status` command from an independent
  test if it can append a recovery correction or otherwise mutate the evidence ledger. Independent
  testers should read the final snapshot, correction chain, transcripts, receipts, and cleanup
  artifacts directly and append only their round to the shared test plan.
- The Delivery Agent may use a deterministic repo-local script for isolation, resource lifecycle,
  mechanical integrity, and cleanup, but that script is not a Host layer and must not judge semantic
  quality. The independent Requirement Tester owns final semantic acceptance; it must not create or
  continue the live run whose evidence it evaluates.
- Classify the failing layer before changing scope. Collaboration-summary misreads and resume-write
  failures are `collaboration/routing` or runtime-adapter defects; interpreter mount, provider, and
  timeout failures are `runtime/infrastructure`; dry-run and receipt-shape defects are
  `platform-contract`; only a completed model that fails semantic gates is `modeling-quality`.
  Repair the narrow layer, reuse the approved modeling work, and do not add Consumer, mutation,
  governance, or orchestration scope in response.

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
