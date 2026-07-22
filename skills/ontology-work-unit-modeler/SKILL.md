---
name: ontology-work-unit-modeler
description: Model one bounded Shared Modeling Directory Work Unit and assess a bounded business change. Use for independent ontology work-unit modeling with schema-valid result output.
---

# Ontology Work Unit Modeler

Preload marker: `R11007_WORK_UNIT_MODELER_PRELOADED`.

## Assignment gate

Before any `Read`, `Glob`, `Grep`, or search, require a complete `assignment`. Require
`assigned_run_root`, `run_id`, `work_unit_id`, `task_path`, and `result_path`. Require the accepted
task to name exact `context_path`, `output_schema_path`, and source/dependency locators. If any
reference is missing, incomplete, or unreadable, return only
`{"status":"BLOCKED","error_code":"missing_reference","missing_references":["<reference>"],"next_action":"supply_complete_assignment"}`.
Do not inspect the cwd, a directory, or another run to discover it.

Resolve every repo-local reference without discovery. Read it only when its resolved path is inside
the resolved `assigned_run_root`. After accepting the task, follow only its exact dependency locators
declared by that task. An original source may be read outside that root only when the accepted manifest permits
that exact locator. Never glob or scan `workspaces/`, another run, or the repo to find input. If an
accepted reference declares a different `run_id`, return
`{"status":"BLOCKED","error_code":"reference_mismatch","mismatches":["run_id"]}`. If a declared
`candidate_hash` disagrees with its candidate, return the same response with `"candidate_hash"`.

Read only the supplied run path, assigned `task.json`, referenced sources/dependencies, current
context, and output schema. Produce that unit's schema-valid `result.json` with exact Evidence and
gaps. For a business change, return exactly `no_change`, `modify_existing`, or `remodel` with a
reason; `no_change` requires identical normalized semantics and gaps.

Do not contact the user, write another unit, edit a candidate outside the assigned result, acquire a
Lease, invoke platform writes, or store reasoning/mailbox files. Follow the common rules by reference:
`../ontology-builder/references/modeling-guidelines.md`, `quality-gates.md`, and
`modeler-handoff.schema.json`.
