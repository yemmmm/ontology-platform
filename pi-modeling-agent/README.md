# pi-modeling-agent

First-party **Pi Local** modeling Agent Runtime for the ontology platform. A repo-local Runner drives
headless Pi RPC child processes through the daily modeling workflow: source understanding, user
interview, Brief/CQ confirmation, Work Unit modeling, independent review, deterministic dry-run/apply,
and post-apply CQ/retrieval/provenance verification.

This is the only actively maintained modeling entry after R2.0-002. Semantic Platform Core keeps its
current deterministic authority and receives no Pi-specific API, database schema, or special write
path (ADR 0007).

## Pinned runtime

- Pi: `@earendil-works/pi-coding-agent@0.81.1` (lockfile is the execution baseline; do not mix an
  upstream clone commit with the npm baseline).
- Node: `>=22.19.0` (enforced by the CLI at start).
- RPC mode: `pi --mode rpc --no-session --approve` over stdin/stdout NDJSON. `--approve` is the
  project-Extension trust flag.

## Lifecycle contract (load-bearing)

`agent_end` is only a low-level run boundary: an auto-retry, a compaction retry, or a queued
follow-up may still continue the same role. A disposable role's artifact is accepted and its child is
reclaimed only when all three hold simultaneously:

1. Pi emitted `agent_settled`;
2. the modeling Extension reports idle with no pending clarification (`modeling_idle` notify);
3. the latest observed `queue_update` reports an empty queue.

The persistent coordinator additionally requires a workflow terminal state before it stops. The
R2.0-001 integrated probe closed stdin on `agent_end`; this Runner never does.

## Install

```bash
cd pi-modeling-agent && npm ci
```

## Run

```bash
node src/cli.mjs --scenario scenarios/dify-foundations-v1.json --config <gitignored-local-config>
```

The gitignored local config selects the existing Project, platform base URL, credential source, and
model/provider without changing Workflow Package files. Template:

```json
{
  "schema_version": 1,
  "project_id": "<existing-project-id>",
  "api_base_url": "http://127.0.0.1:8001/api",
  "api_key_env_file": "backend/.env",
  "api_key_env_name": "ONTOLOGY_MCP_API_KEY",
  "provider": "<provider>",
  "model": "<model>",
  "max_parallel_workers": 1
}
```

Credentials never enter the tracked scenario, prompts, event file, artifacts, or committed config.

## Layout

```
src/         Runner, RPC session, event recorder, stage summary, CLI
extensions/  Pi modeling tools (typebox schemas)
workflow/    Pi-only Workflow Package: role prompts, references, schemas
lib/         migrated deterministic Python core (Shared Directory, handoff, profiles, platform adapter)
scenarios/   tracked, reusable business input only
tests/       phase-1 contract tests + migrated deterministic tests
```

## Test

```bash
cd pi-modeling-agent && npm test
python3 -m unittest discover -s pi-modeling-agent/tests
```

Phase-1 automated tests use a fake Pi RPC subprocess (scripted event stream), mock platform
responses, and synthetic fixtures. They prove lifecycle, role isolation, clarification, events,
summaries, recovery, and the migrated deterministic core. Real Pi/model/platform acceptance is a
separate round (test plan section G).

## Boundary

Pi uses the same supported REST/MCP contracts as any authorized modeling client. It receives no
direct repository/database access and no bypass for validation, review binding, dry-run/apply,
idempotency, workspace version, Evidence, or query verification.
