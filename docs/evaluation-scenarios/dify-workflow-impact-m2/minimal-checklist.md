# M2 minimal handoff checklist

Use this only after the environment owner has provided a fresh isolated
`rdf_primary` backend and an API key through `ONTOLOGY_M2_API_KEY`.

1. Read `/api/health` and `/api/semantic/canonical-mode`; stop unless the
   isolated mode is `rdf_primary`.  Separately verify that the normal service
   remains `legacy_only`.
2. Run `run_rehearsal.py` from this package.  It creates a fresh Project,
   Ontology, Build Session, official Evidence, synthetic-fixture Evidence, and
   immutable candidate attempts.
3. Keep the bad-shape and invalid-Invocation dry-run findings.  Do not apply
   either candidate and do not replace their idempotency keys.
4. Require every accepted candidate to dry-run first, then reacquire the fresh
   workspace version, use the Build Session lease, and call `apply_atomic`.
5. Read the Graph Set and pass its unique `shapes` member explicitly to managed
   validation.  Record validation/reasoning request and run IDs, statuses, and
   the Graph Set source signature.
6. Require conformant validation, successful/consistent reasoning, the RDFS
   subclass entailment, and all four scoped SPARQL assertions before handoff.
7. Preserve `runtime/runtime-record.json` and append the outcome to
   `rehearsal-log.md`; also retain `runtime/runtime-record-<run-tag>.json` for
   each run.  For a correction, pass the prior tag using `--corrects-run-tag`.
   The record contains IDs/statuses only; never add a key,
   lease token, cookie, raw authorization header, or unrecorded local state.

If a generic command cannot express a required behavior, stop and refine a
separate generic platform requirement.  Do not use semantic edits, dataset
loads, `validate=false`, direct database/RDF writes, or a domain-specific
platform extension.
