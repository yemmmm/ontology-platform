# Local/Formal modeling Profiles

At the start, the main Agent reports `execution_profile=local` for ordinary modeling or
`execution_profile=formal` for formal delivery/full-chain acceptance. `strict_eval` composes with
Formal; `fast_local` remains a separate simulated-user evaluation mechanism.

## Local

Create an ignored Adapter config from `.claude/local-modeling.example.json` under
`workspaces/modeling-adapter/local.json`. Initialize the R1.1-006 shared run with
`execution_profile: local`; do not put a credential, Lease token, or raw response in the run.
Start the Claude main session with `--setting-sources user,project` so the checked-in project
agents, Skills, and Hook registry are loaded.

Run Adapter `start` first. It creates/reconciles the empty Build Session and returns its stable ID;
it does not begin a modeling action or write Brief/CQ/candidate data. Inside the single top-level
Claude main session, activate the recorder through a trusted Hook using that ID:

```bash
python3 .codex/hooks/modeling_harness.py activate \
  --run-id RUN_ID --activation-nonce ONE_TIME_NONCE \
  --build-session-id BUILD_SESSION_ID --project-id PROJECT_ID \
  --runtime claude --execution-profile local
```

Then invoke Adapter `recording-health RUN_DIR --run-id RUN_ID --harness-run-id RUN_ID` from that same Claude session before
the first business/modeling action. The Hook issues a receipt for the Adapter command and the Adapter
consumes it through the Harness, so an old `ready=true` cannot pass. The Adapter is the only Local
platform-write surface; normal roles receive only run/Work Unit/Ontology/schema/output/change
references. At stage boundaries, worker resume, review, apply, and final verification repeat the
same health action. On failure, pause for retry or an explicit `recording_unavailable` choice.

The business commit boundary is Brief/CQ binding before Work Unit modeling. Bind platform CQ IDs in
Coverage before candidate/review/Batch generation. Continue with shared candidate merge, independent
review, deterministic dry-run/apply, retrieval, and provenance verification; Local never creates
Workflow Artifacts, Events, Checkpoints, or a retrospective explicitly.

## Formal

Use the existing `ontology-builder` formal workflow and full MCP surface. It retains Workflow
Artifacts, Events, Checkpoints, reliable handoff, and formal verification. Switching Profiles creates
a new run; no prior records are backfilled or claimed retroactively.
