# M3-safe minimal handoff checklist

This checklist transfers the generic M2 operating sequence to M3. The autonomous
modeling Agent may read this file and `m3-reusable-lessons.md`, but must not read
or execute `run_rehearsal.py`, which contains M2's answer-shaped candidate
payload.

Use this only after the environment owner has provided a fresh isolated
`rdf_primary` backend and an API key through a process-local environment
variable.

1. Read `/api/health` and `/api/semantic/canonical-mode`; stop unless the
   isolated mode is `rdf_primary`.  Separately verify that the normal service
   remains `legacy_only`.
2. Create a fresh Project, Ontology and Build Session through formal platform
   calls. Register official-source and synthetic-fixture Evidence separately.
   Put modeling decisions only in Modeling Item `rationale`, Build Checkpoints
   and the append-only execution log; never create Evidence from Agent
   inference or modeling rationale.
3. Keep findings from deliberately invalid negative candidates created from
   the Agent's own constraints. Do not apply them and do not replace their
   idempotency keys.
4. Require every accepted candidate to dry-run first, then reacquire the fresh
   workspace version, use the Build Session lease, and call `apply_atomic`.
5. Read the Graph Set and pass its unique `shapes` member explicitly to managed
   validation.  Record validation/reasoning request and run IDs, statuses, and
   the Graph Set source signature.
6. Require conformant validation, successful/consistent reasoning and the
   Agent's own competency-query checks before handoff. The independent
   evaluator runs its withheld behavior assertions after handoff.
7. Preserve one safe record per run and append the outcome to the M3 execution
   log. Link a corrective run to the prior run tag. The record contains
   IDs/statuses only; never add a key, lease token, cookie, raw authorization
   header, answer payload, or unrecorded local state.

If a generic command cannot express a required behavior, stop and refine a
separate generic platform requirement.  Do not use semantic edits, dataset
loads, `validate=false`, direct database/RDF writes, or a domain-specific
platform extension.

See `m3-reusable-lessons.md` for the full rationale, failure taxonomy,
autonomy boundary and completion checklist.
