# Ontology Modeling Team L3

This repository-local, test-only scenario evaluates one isolated, fresh three-Agent
attempt over the bounded published Dify Workflow-as-Tool `C -> B -> A` slice. It is not
a product Runtime, credential broker, Judge, Consumer, mutation suite, or Dify-specific
platform feature.

`agent-input/` is the entire frozen team-visible pack. `tester-only/` is never mounted
for a team process. Runtime evidence is written only under ignored `runtime/runs/<id>/`;
it records hashes, question/answer continuation, role/session events, protocol receipts,
preflight, cleanup and terminal category, never plaintext credentials.

The Protocol-only mechanics helper in `run_l3.py` owns stable IDs, canonical envelopes,
atomic publication, request/receipt checks, immutable Batch replay, revision/lease and
checkpoint bodies. It treats Items and query semantics as opaque Protocol-Agent input.
Coordinator staging excludes the public protocol; the separately staged Protocol pack receives
only the public protocol, mechanics contract, opaque approved handoff and a redacted no-key /
temporary-model-key lifecycle contract.

Run offline checks:

```bash
uv run --directory backend python -m unittest discover \
  ../docs/evaluation-scenarios/ontology-modeling-team-l3/tests
uv run --directory backend ruff check ../docs/evaluation-scenarios/ontology-modeling-team-l3
```

Live execution is currently disabled by the committed
[`execution-policy.json`](execution-policy.json): the three-start budget is consumed and
the authoritative outcome is `PAUSED / NOT_PASSED / collaboration/routing`. Do not invoke
`run --execute`; it fails before creating a runtime root, isolated probe, Project, key, or
Agent process.

The ledger enforces at most three fresh starts and the 20-minute first-delegation gate.
If that gate is missed, preparation stops rather than expanding the harness.
It is scenario-global, append-only and lock-protected under ignored `runtime/`: a coordinator
start is counted globally, while `first_modeling_started_at` is recorded only after the transcript
contains one authoritative `spawn_agent` child Session identity. Inspect the authoritative offline
state without launching anything:

```bash
uv run --directory backend python ../docs/evaluation-scenarios/ontology-modeling-team-l3/run_l3.py status
```

For preserved historical attempts, `runtime/historical-classification-ledger.jsonl` appends a
separate correction rather than rewriting raw run state. Each correction binds the exact raw
`state.json` and coordinator transcript paths plus SHA-256 hashes; `status` derives its authoritative
category from this ledger and fails closed if those raw facts drift.

Any future live reauthorization requires a reviewed edit to `execution-policy.json` that records
the repaired child-startup proof, a completed plan re-review, and explicit user authorization for
a new fresh-start budget. Runtime cleanup alone cannot reopen execution.
