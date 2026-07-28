# R2.1-001 M6 autonomous semantic-gap discovery

This package is the minimal Codex-subagent experiment for M6. The modeling Agent may read only
`agent-input/` and platform results produced during its own attempt. `host-only/` is evaluator-owned
and must never be included in the modeling handoff.

Offline checks:

```bash
uv run --directory backend pytest \
  ../docs/evaluation-scenarios/dify-workflow-impact-m6/tests
```

The Host creates only an empty Project and Ontology. A fresh `fork_turns=none` modeling subagent
receives their IDs, creates its own Build Session, asks one source-grounded business question at a
time, and owns every semantic request and payload. Because the connected MCP inventory available to
the collaboration subagent is read-only for this fresh scope, the subagent writes exactly one public
HTTP request at a time; the Host adds credentials and relays it unchanged. The relay cannot choose or
repair semantic content.

`attempts.jsonl` is append-only. At most three `modeling_started` events are accepted. A fourth
modeling attempt is rejected, and reaching attempt three requires the main agent to pause and report.

The accepted live run used one modeling attempt:

- Project: `1874b5df-16b8-41fa-bad8-95e886ba70d4`
- Ontology: `27b9c681-f39a-43ba-9a69-16b4f3c69c5e`
- Build Session: `89b67fef-e82a-470c-9eb9-928078a8b206` (`completed`, revision `3`)
- schema Batch: `ac96ecb3-6b65-4c8b-862c-d18760a44e91`
- rejected negative Batch: `93410be3-6404-4f18-9b86-5fd5351152fe`
- applied instance Batch: `849a6350-14cc-48c0-9252-1ac8ef41d725`
- validation: `d548889a-67de-465e-a1f1-d4064408cc8a` (`conforms=true`)
- reasoning: `219c3361-c674-4fbc-9d80-76065c3a1002` (`consistent=true`)

The independent blind Consumer recovered C Version 2 / `quality_rating`, the documented
`quality_score` -> `quality_rating` continuity, and the missing-score behavior as
`explicit_unknown` from a complete, non-truncated ontology-scoped public query.
