# Repository Guidelines

## Project Structure & Module Organization

This repository contains a FastAPI backend and a Vite/React frontend for an ontology and knowledge graph platform. Key paths:

- `backend/app/api/`: HTTP routes, dependencies, and schemas.
- `backend/app/domain/`: ontology and graph domain models.
- `backend/app/repositories/`: PostgreSQL and Neo4j persistence.
- `backend/app/services/`: validation and application workflows.
- `backend/app/mcp/`: MCP server entrypoint.
- `backend/migrations/`: Alembic migrations.
- `frontend/src/`: React UI entrypoint and styles.
- `docs/`: architecture, API, MCP, UI docs, and ADRs.

## Build, Test, and Development Commands

- `./scripts/start-local.sh`: checks PostgreSQL and Neo4j, syncs dependencies, runs migrations, and starts backend plus frontend.
- `cd backend && uv sync --extra dev`: installs backend runtime and development dependencies.
- `cd backend && uv run alembic upgrade head`: applies database migrations.
- `cd backend && uv run uvicorn app.main:app --reload`: runs the API at `http://localhost:8000`.
- `cd backend && uv run python -m app.mcp.server`: runs the MCP server.
- `cd frontend && npm install`: installs frontend dependencies.
- `cd frontend && npm run dev`: starts the Vite dev server.
- `cd frontend && npm run build`: type-checks and builds the frontend.

## Coding Style & Naming Conventions

Backend code targets Python 3.11 and uses Ruff with a 100-character line length. Keep API handlers thin, put workflow logic in services, and keep storage details in repositories. Use `snake_case` for Python modules, functions, and variables; use `PascalCase` for Pydantic and domain classes.

Frontend code uses TypeScript, React, and ES modules. Use `PascalCase` for components, `camelCase` for functions and state, and keep styling in `frontend/src/styles.css` for now.

## Testing Guidelines

Backend dev dependencies include `pytest`; place tests under `backend/tests/` with names like `test_metadata.py` or `test_graph_validation.py`, then run `cd backend && uv run pytest`. Prefer service-level tests for validation rules.

Any change under `backend/` must include new or updated tests when behavior changes and must be
verified with `cd backend && uv run pytest` before the work is considered complete. Do not report a
backend change as complete while tests are failing. If the test command cannot be run because an
external dependency is unavailable, document the exact blocker and the narrower checks that were run.

No frontend test runner is configured yet. For UI changes, run `cd frontend && npm run build` and document manual browser checks.

## Commit & Pull Request Guidelines

Recent commits use short imperative summaries, for example `Add local startup workflow`. Keep commit subjects concise and action-oriented.

Pull requests should include a clear description, relevant issue links, migration notes for schema changes, and screenshots or recordings for visible UI changes. Mention the commands you ran.

## Security & Configuration Tips

Copy `.env.example` to `backend/.env` for local development. Do not commit real credentials, API keys, database dumps, `backend/.venv/`, `frontend/node_modules/`, or generated `frontend/dist/` artifacts unless explicitly required.
