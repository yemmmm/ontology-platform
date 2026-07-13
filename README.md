# Ontology Platform

Ontology Platform is an MVP for managing lightweight ontology schemas and knowledge graph instances. It exposes an HTTP API for the web UI and semantic MCP tools for external agents.

The MVP uses a custom schema model: projects contain ontologies; ontologies define classes, properties, and relation types; graph entities and relations are validated against that schema before being stored.

## Repository Layout

```text
backend/
  app/
    api/              # FastAPI HTTP routes
    mcp/              # MCP server entrypoint
    repositories/     # PostgreSQL and graph store access
    services/         # Validation and application services
frontend/
  src/                # React/Vite operational UI
skills/
  ontology-builder/   # Installable external-agent workflow
docs/
  api.md
  architecture.md
  mcp.md
  ui.md
```

## Local Startup

Start the local development stack:

```bash
./scripts/start-local.sh
```

The script checks PostgreSQL and Oxigraph first, syncs backend dependencies with `uv`, runs migrations,
builds the frontend production assets, and starts the backend API plus a frontend preview server.
The preview server proxies `/api` to the backend without enabling Vite hot reload.

If you prefer to run the services manually, create local backend configuration first:

```bash
cp .env.example backend/.env
```

Install and run database migrations:

```bash
cd backend
uv sync --extra dev
uv run alembic upgrade head
```

Run the backend API:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000/api`. FastAPI docs are available at `http://localhost:8000/docs`.

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Run the MCP server:

```bash
cd backend
uv run python -m app.mcp.server
```

## Install the ontology-builder Skill in Codex

The v0.3 workflow ships as a repository-owned Skill and runs against the semantic MCP server above.
Install it for Codex with a symlink so repository updates remain visible:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -sfn "$PWD/skills/ontology-builder" "${CODEX_HOME:-$HOME/.codex}/skills/ontology-builder"
```

Configure the `ontology-platform` MCP server as shown in [docs/mcp.md](docs/mcp.md), restart Codex,
and invoke `$ontology-builder` with a project ID. The Skill always resumes from platform state and
routes approvals, conflict decisions, fact audit, and publication to the review workbench.

## Environment Variables

The backend reads `.env` from the process working directory. The commands above run backend processes from `backend/`, so the local file should be `backend/.env`.

| Variable | Purpose | Default/example |
| --- | --- | --- |
| `APP_ENV` | Runtime environment label. | `development` |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL. | `postgresql+psycopg://ontology:ontology@localhost:5432/ontology_platform?client_encoding=utf8` |
| `ADMIN_TOKEN` | Intended shared secret for administrative HTTP calls. | `change-me-admin-token` |
| `MCP_API_KEY` | Intended shared secret for MCP clients. | `change-me-mcp-key` |
| `LLM_BASE_URL` | OpenAI-compatible API base URL for demo agent answers. | `https://api.openai.com/v1` |
| `LLM_API_KEY` | Optional demo agent API key. | empty |
| `LLM_MODEL` | Optional demo agent model. | empty |
| `LLM_TEMPERATURE` | Demo agent temperature. | `0.2` |
| `OXIGRAPH_URL` | Oxigraph HTTP endpoint for the Phase 1 semantic runtime POC. | `http://localhost:7878` |
| `SEMANTIC_BASE_IRI` | Base IRI for generated semantic resources. | `http://ontology-platform.local/semantic/` |
| `SEMANTIC_GRAPH_IRI_PREFIX` | Guardrail prefix for platform-managed graph IRIs. | `http://ontology-platform.local/semantic/graph/` |
| `SEMANTIC_QUERY_TIMEOUT_SECONDS` | Default SPARQL query timeout. | `10` |
| `SEMANTIC_QUERY_RESULT_LIMIT` | Default SPARQL query result limit. | `1000` |
| `SEMANTIC_SHACL_INFERENCE` | Default pySHACL inference mode. | `none` |
| `SEMANTIC_REASONER_COMMAND` | Optional command for the OWL reasoner boundary. | empty |
| `SEMANTIC_REASONER_TIMEOUT_SECONDS` | OWL reasoner command timeout. | `60` |


## Auth Tokens

`ADMIN_TOKEN` is enforced on metadata, graph, import/export, and agent-test HTTP routes. Health routes remain public for local readiness checks.

HTTP convention:

```http
Authorization: Bearer <ADMIN_TOKEN>
```

MCP tools accept an `api_key` argument and compare it with `MCP_API_KEY`.

## Documentation

- [HTTP API](docs/api.md)
- [MCP Tools](docs/mcp.md)
- [UI](docs/ui.md)
- [Architecture](docs/architecture.md)
- [Glossary](docs/glossary.md)
- [Platform Guide](docs/platform-guide.md)
- [v0.5 Requirements](docs/requirements-v0.5.md)
