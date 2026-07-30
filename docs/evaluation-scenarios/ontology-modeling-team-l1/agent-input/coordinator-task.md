# L1 workflow version-state task

You are the fresh Ontology Modeling Team coordinator. Work only in `/opt` and `/work`; do not read
the repository, prior runs, tester-only material, platform credentials, or platform MCP tools.

The visible source is a pinned Dify Version Control page. `SyntheticReleaseWorkflow` is a synthetic
test Workflow, not an official Dify example. Decide how a working Current Draft and the live Latest
Version should be represented, and what minimum deterministic constraint rejects a Version without
the required workflow/state classification.

For S0, spawn `modeling_agent` and `protocol_planning_agent`, both with `fork_turns="none"`. Ask the
former for a business/ontology candidate and the latter for a generic no-write command plan. Do not
make a platform call or produce Modeling Items. Write `/work/s0-result.json` with only
`task_id`, `candidate_sha256`, `requested_outcome` and `no_platform_write: true`.

For S1, spawn only `modeling_agent` with `fork_turns="none"`. Review its business/ontology candidate.
If it preserves the source distinction, write `/work/approved-candidate.json` and
`/work/protocol-dispatch.json`. The candidate must be an object with `business_question`,
`synthetic_workflow`, `concepts`, `states`, and `minimum_constraint`; it must contain no Modeling
Items, credential, platform ID, batch ID, query, hidden answer, or implementation receipt. The
dispatch must be an object with exactly `task_id`, `candidate_sha256`, and `requested_outcome`; set
`candidate_sha256` to `PENDING_LAUNCHER_CANONICALIZATION`. The delivery launcher deterministically
canonicalizes the approved candidate and replaces only that hash before protocol launch; requested
outcome is `apply_version_state`.
Output exactly `L1_COORDINATOR_DISPATCHED` after both files exist.
