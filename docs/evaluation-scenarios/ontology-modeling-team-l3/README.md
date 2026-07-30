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

The committed [`execution-policy.json`](execution-policy.json) records three consumed starts,
`max_starts=5`, and the user's authorization for exactly two further fresh starts. Start 4 may
run only after the required offline checks and independent review pass. Start 5 is available only
after a repairable start-4 runtime, platform-contract, or collaboration transport failure; a
completed-model `modeling-quality` failure blocks another start before any run root, isolated
probe, Project, key, or Agent process is created.

The authorized budget is now exhausted. The append-only runtime ledger records five starts and the
retained `l3-real-20260730k` recovery has a terminal `PASS / PASSED` correction. Do not edit the
policy or launch another fresh team without a new explicit user authorization. Protocol retries
inside k reused the same approved modeling candidate and did not consume another modeling start.

The same versioned policy records the recovery developer-handoff timestamp. The 20-minute
first-delegation gate is derived from that timestamp, never from the earlier three-start run.

The ledger enforces the five-start ceiling and the 20-minute first-delegation gate.
If that gate is missed, preparation stops rather than expanding the harness.
It is scenario-global, append-only and lock-protected under ignored `runtime/`: a coordinator
start is counted globally, while `first_modeling_started_at` is recorded only after raw evidence
proves the outer coordinator `thread.started`, raw coordinator `spawn_agent` plus
`sub_agent_activity`, and raw child `session_meta` parent/role chain. A CLI transcript alone and a
`task_name` never prove a Modeling Agent child. Inspect the authoritative offline state without
launching anything:

```bash
uv run --directory backend python ../docs/evaluation-scenarios/ontology-modeling-team-l3/run_l3.py status
```

For preserved historical attempts, `runtime/historical-classification-ledger.jsonl` appends a
separate correction rather than rewriting raw run state. The v2 corrections retain g as the missing
configured-role negative fixture and mark h/i as raw role/fork positive fixtures that supersede the
old no-child harness diagnosis. Each correction binds raw state, transcript, and role-session evidence;
`status` fails closed if those facts drift.

For a retained non-terminal run that has a mechanically released answer, use the continuation
entrypoint rather than creating another start. It resumes only the recorded coordinator Session;
each newly produced pending question remains non-terminal until Delivery releases one exact frozen
answer. Once the coordinator publishes the canonical dispatch, the launcher creates the owned
Protocol scope, starts the separately configured Protocol Agent, audits platform facts, and revokes
the model key before deleting the exact owned Project. After the Protocol process has terminated,
the uniquely owned `protocol-home` (including its temporary config and provider-auth files) is
destroyed; retained audit evidence is scanned for the exact temporary model key and contains only
the redacted cleanup receipt.

```bash
uv run --directory backend python ../docs/evaluation-scenarios/ontology-modeling-team-l3/run_l3.py \
  continue --run-id <retained-run-id> --execute
```

Any further live authorization requires a reviewed edit to `execution-policy.json` and explicit user
authorization for a new fresh-start budget. Runtime cleanup alone cannot reopen execution.
