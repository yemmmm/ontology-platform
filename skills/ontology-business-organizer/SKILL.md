---
name: ontology-business-organizer
description: Organize referenced business sources and confirmed user input into a Shared Modeling Directory Brief, Coverage, and bounded clarification questions. Use for the business-discovery role in a Local or Formal ontology run.
---

# Ontology Business Organizer

Preload marker: `R11007_BUSINESS_ORGANIZER_PRELOADED`.

## Assignment gate

Before any `Read`, `Glob`, `Grep`, or search, require a complete `assignment`. Require
`assigned_run_root`, `run_id`, `brief_path`, `coverage_path`, `source_index_path`,
`brief_output_path`, `coverage_output_path`, and `questions_output_path`. If any reference is
missing, incomplete, or unreadable, return only
`{"status":"BLOCKED","error_code":"missing_reference","missing_references":["<reference>"],"next_action":"supply_complete_assignment"}`.
Do not inspect the cwd, a directory, or another run to discover it.

Resolve every repo-local reference without discovery. Read it only when its resolved path is inside
the resolved `assigned_run_root`. After accepting the direct refs, follow only exact dependency
locators named inside them. An original source may be read outside that root only when the accepted
source index permits that exact locator. Never glob or scan `workspaces/`, another run, or the repo
to find input. If an accepted reference declares a different `run_id`, return
`{"status":"BLOCKED","error_code":"reference_mismatch","mismatches":["run_id"]}`.

Read the assigned run's `shared/brief.md`, source index, Coverage, and referenced source locators.
Record confirmed goal/success, scope/non-goals, authority, terms/aliases, participants/events,
identity/lifecycle, rules/exceptions, ambiguity, and every Coverage disposition. Return only bounded
questions that need the main Agent or user.

Write Brief/Coverage/questions, never Modeling Items, a Batch, platform data, or a mailbox. Use the
shared contracts in `../ontology-builder/references/interview-fields.md`,
`../ontology-builder/references/ambiguities.md`, and `../ontology-builder/references/quality-gates.md`;
do not copy their rules here.
