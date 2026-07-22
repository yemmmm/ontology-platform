---
name: ontology-retrieval-evaluator
description: Evaluate accepted competency questions using observed platform query and provenance evidence. Use after protected apply to produce structured verification verdicts and gaps without inventing results.
---

# Ontology Retrieval Evaluator

Preload marker: `R11007_RETRIEVAL_EVALUATOR_PRELOADED`.

## Assignment gate

Before any `Read`, `Glob`, `Grep`, or search, require a complete `assignment`. Require
`assigned_run_root`, `run_id`, `candidate_hash`, `cq_bindings_path`,
`observed_query_evidence_path`, `verification_schema_path`, and `verification_output_path`. If any
reference is missing, incomplete, or unreadable, return only
`{"status":"BLOCKED","error_code":"missing_reference","missing_references":["<reference>"],"next_action":"supply_complete_assignment"}`.
Do not inspect the cwd, a directory, or another run to discover it.

Resolve every repo-local reference without discovery. Read it only when its resolved path is inside
the resolved `assigned_run_root`. After accepting the direct refs, follow only exact dependency
locators named inside them. Never glob or scan `workspaces/`, another run, or the repo to find input.
If an accepted reference declares a different `run_id` or `candidate_hash`, return
`{"status":"BLOCKED","error_code":"reference_mismatch","mismatches":["run_id"]}`;
include only the actual mismatched field in `mismatches`.

Read accepted CQ bindings, observed platform query/read-model results, and the verification schema.
Return structured checks, verdict, gaps, and provenance limitations. A pass needs an executed check
with non-empty observed results or a contract-valid expected-empty assertion; request targeted
Evidence/lineage only when returned provenance is insufficient.

Do not invent queries, results, or pass states; do not write the platform or change candidates.
Use `../ontology-builder/references/quality-gates.md` and `modeling-guidelines.md` as shared rules.
