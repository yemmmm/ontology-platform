# Dify Workflow-as-Tool impact: M2 controlled rehearsal

This package is the implemented and independently accepted M2 scenario for R2.1-001. It turns the M1
semantic behavior into structured Modeling Batch commands; it is not a Dify
integration and does not load Turtle, call semantic edits, or write a database
or RDF store directly.

The runner creates a new Project, Ontology, Build Session, and two Evidence
References on each invocation.  It deliberately retains them for independent
testing and M3.  It does **not** stop the isolated backend or touch the regular
`ontology-platform.service`.

## Preconditions

- The regular service has already been checked as `legacy_only` by the operator.
- The isolated service is already running at `http://127.0.0.1:8012` with
  `rdf_primary`, an operator API key with the required project/model scope, and
  the configured development reasoner.
- Export the key only into the invoking process, for example:

  ```bash
  export ONTOLOGY_M2_API_KEY='...'
  ```

The key is sent only as an HTTP Bearer credential.  It is not a command-line
argument, is never printed, and is excluded from the runtime record and log.

## Candidate execution

From the repository root:

```bash
uv run --directory backend python \
  ../docs/evaluation-scenarios/dify-workflow-impact-m2/run_rehearsal.py \
  --base-url http://127.0.0.1:8012
```

The command fails closed on an unexpected mode, a failed dry-run, a non-applied
atomic batch, an unconformant managed validation, missing `shapes` graph-set
member, missing RDFS subclass entailment, or a failed scoped SPARQL assertion.
It records only safe identifiers, statuses, findings, graph IRIs, and query
results in `runtime/runtime-record.json`, then appends a concise entry to
`rehearsal-log.md`.

Every execution also retains `runtime/runtime-record-<run-tag>.json`; the
unqualified `runtime-record.json` is only the latest safe snapshot.  For a
corrective round, pass `--corrects-run-tag <prior-run-tag>` so both the runtime
record and append-only log preserve the correction link.

Run the independent read-only validation persistence check using the two values
in that record:

```bash
cd backend && uv run python \
  ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/verify_validation_run.py \
  --run-id <validation-run-id> --expected-shape-graph-iri <shapes-member-iri>
```

`verify_validation_run.py` only opens an ORM session for a `SELECT`; an engine
guard rejects SQL write/DDL statements and the script rolls its transaction
back before closing.

## Model/contract choices frozen here

- The 17 constrained object predicates are all `create_property` commands with
  `object_class_id`.  Fixture `create_relation` items use the matching emitted
  `/property/{id}` IRI, never a relation-type IRI.
- The bad-shape candidate creates a `ToolInvocation` without `invokesTool` and
  must be rejected during dry-run.  The later invalid-Invocation fixture is also
  dry-run-only and is never applied.
- The default Graph Set exposes the member role as `shapes` (plural), while the
  current endpoint's fallback probes `shape` (singular).  The runner therefore
  selects the unique `shapes` member and sends it explicitly in every managed
  validation request.
- The final semantic assertions are scoped SPARQL against the fresh Project and
  Ontology: callers exactly B/A, one C -> B -> A context row, draft/latest
  separation, and an explicit `unknownDetail` gap.  RDFS subclass evidence is
  asserted from the managed reasoning result.

See [minimal-checklist.md](minimal-checklist.md) for the M3-safe operational
handoff.  It deliberately contains no ORM/database step and no answer payload.
