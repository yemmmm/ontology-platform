# Ontology Modeling Team L0

This is the repository-local, test-only L0 launcher for R2.2-001. It starts a
fresh persistent Codex coordinator in a bubblewrap allow-list namespace, gives
it two named custom roles, and verifies child-rollout evidence rather than
trusting a coordinator summary. L0 does not write ontology data or assess
modeling quality.

The committed `agent-input/` is the complete frozen input set and is checked
against `manifest.json`. `tester-only/` is intentionally never mounted.
`runtime/runs/<run-id>/` is ignored and holds staging, `/work`, temporary
`CODEX_HOME`, raw JSONL, and redacted audit evidence.

The host resolves the existing project-scoped MCP principal, creates one unique
same-project `read` key with the security helper, injects it only into the
run-local root Codex MCP configuration, and records only key ID/project/scope. The
plaintext is not copied to audit or transcripts. Terminal resume/cleanup
revokes the key.

Run the offline checks from the repository root:

```bash
uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l0/tests
uv run --directory backend ruff check ../docs/evaluation-scenarios/ontology-modeling-team-l0
```

For a real run, check health before and after, then use a fresh run ID:

```bash
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
uv run --directory backend python ../docs/evaluation-scenarios/ontology-modeling-team-l0/run_l0.py start --run-id l0-<unique>
uv run --directory backend python ../docs/evaluation-scenarios/ontology-modeling-team-l0/run_l0.py resume --run-id l0-<unique> --answer accepted
uv run --directory backend python ../docs/evaluation-scenarios/ontology-modeling-team-l0/run_l0.py audit --run-id l0-<unique>
```

`start` never uses `--ephemeral`; only `resume` may continue a run in
`WAITING_FOR_ANSWER`. Any error keeps its raw evidence and revokes the owned
temporary key. `audit` accepts only a terminal state with a revoked key.
