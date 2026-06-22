# UI

The frontend is a React/Vite operational workspace in `frontend/`.

Run locally:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` to override the default `http://localhost:8000/api`.

## Implemented Pages

- Projects: list/create/delete projects, list/create/delete ontologies, select active context.
- Ontology Designer: list/create/delete classes, properties, and relation types.
- Graph Manager: list/create entities and relations, inspect a simple SVG graph view.
- MCP/Agent Test: send a question to `POST /api/agent-test/run`, inspect answer, tool calls, graph context, and prompt preview.
- Health: call `/api/health/dependencies` and show PostgreSQL/Neo4j status.

## Data Flow

```text
React UI
  -> FastAPI /api routes
  -> PostgreSQL for ontology metadata
  -> Neo4j for graph instances
```

The UI never connects directly to PostgreSQL or Neo4j.

## Future Work

- edit/update forms for existing metadata and graph records
- richer graph layout and filtering
- import/export controls
- MCP tool explorer screen separate from agent testing
- full user auth/RBAC if the MVP grows beyond trusted local deployments
