# Ontology Modeling Team L1

Repository-local, test-only launcher for R2.2-001 L1. It stages one pinned Dify Version Control page,
uses separate bubblewrap namespaces for a fresh no-MCP coordinator/modeler and a separately launched
protocol Agent, and starts a one-run loopback `rdf_primary` REST/MCP environment. It is not a platform
runtime or a generalized credential broker.

The committed `agent-input/` is the complete Agent-visible source. Runtime evidence is created under
the ignored `runtime/runs/<run-id>/`; it may contain redacted transcripts, normalized receipts and
cleanup state, but never plaintext credentials. `tests/` is tester-only and is never staged.

Offline checks:

```bash
uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l1/tests
uv run --directory backend ruff check ../docs/evaluation-scenarios/ontology-modeling-team-l1
```

Before a live attempt, preserve the resident checks, then use a unique run id:

```bash
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
uv run --directory backend python ../docs/evaluation-scenarios/ontology-modeling-team-l1/run_l1.py run --run-id l1-<unique> --execute
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

`--execute` is required because a run creates an owned Project and ephemeral keys. The launcher fails
closed on an unavailable `rdf_primary` isolated runtime, missing run model key, candidate/dispatch
drift, failed dry-run/apply, evidence leakage, or cleanup uncertainty. It deletes only the Project
whose exact create receipt carries this run tag, then verifies the model key, host-admin key and
resident services.

The launcher state is diagnostic evidence, not a separate product Judge. If a bookkeeping heuristic
fails after the platform workflow has completed, the Delivery Agent and an independent tester may
inspect the retained rollout metadata, MCP receipts, Batch/workspace transitions, semantic read and
cleanup records directly. L1 acceptance does not require writing or rerunning an automated Judge.
