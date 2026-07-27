# R2.1-001 M4 proactive semantic clarification scenario

This package is an isolated successor experiment to M3. It intentionally does not import M1–M3
runners, answer artifacts, or test specifications. The host-side responder holds baseline or
withheld-variant decisions outside the Agent mount. `m4_api_file_spool_gateway.py` separately
injects the host credential after an allowlisted API-spool request. The Agent sees only the sanitized
manifest, brief, contracts, API spool and a matching read-only clarification response.

Run focused protocol and semantic gates:

```bash
uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests
```

Prepare a fresh mounted namespace (without starting Codex) for audit or an external Agent run:

```bash
python3 docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py \
  --run-root /tmp/m4-run --variant baseline --prepare-only
```

Run a formal fresh-Agent attempt against an already-started isolated `rdf_primary` backend (default
host port `8012`) by omitting `--prepare-only`; the launcher starts both host spools, runs Codex inside
the audited bwrap namespace, and retains transcript, spool and final-run audits. The independent
tester still owns baseline/variant semantic queries, read-only-consumer evidence and mutations.

The bwrap namespace remains cleared by default. It forwards only a non-empty `HTTPS_PROXY` or
`HTTP_PROXY` (accepting either case and setting both spellings for Codex compatibility), plus no other
host environment. Mount audit records the forwarded variable names and value hashes, never proxy URLs.

Both file spools accept canonical UTF-8 JSON with no whitespace changes, except one final transport
terminator (`LF` or `CRLF`). Their audits record separate raw-request and canonical-request SHA-256
values, so this normalization remains observable without retaining request bodies.

The staged generic command contract gives the fresh Agent the actual public request fields and
revision/lease state transitions needed for Project, Ontology, Build Session, Modeling Batch,
Shape/resource/relation, validation, graph-set reasoning, governed query, checkpoint, completion and
final GET. It contains no domain-specific ontology recipe. The Agent updates its runtime record and
decision log after every receipt and follows a completion-first order: principal schema dry-run,
the unchanged Shape apply, a separate invalid-instance dry-run with the public HTTP-2xx
`validation_failed`/blocking-`shacl_violation` result, one valid-instance dry-run and unchanged
apply, validation, reasoning, one governed positive query, pre-checkpoint session GET, checkpoint,
complete, then final GET.

The final launcher audit does not trust Agent result claims. It binds each receipt's canonical request
hash, method and exact public endpoint to the host-owned gateway audit, retains only a safe Batch
mode/command-kind request summary, and parses the matching protected API response envelope to verify
the semantic predicates, checkpoint revision, completion, and final GET. This also proves the Shape
apply was an `apply_atomic` Modeling Batch containing `create_shape`, while the invalid instance was
a `dry_run` that never applied. The persisted audit stores only hashes, filenames, safe request
summaries, and derived gate errors—not response bodies. Agent `BLOCKED` or `INCONCLUSIVE` terminal
states propagate to the final audit.

The formal action plan is anchored by exactly one principal Shape-containing schema Batch: dry-run it
once, apply that unchanged candidate once, then immediately make the invalid-instance dry-run. There
is no second schema Batch, post-apply schema exploration, operation endpoint, Rule Definition/Rule
Run, or second producer query.

The first instance candidate normally validates and applies unchanged. A generic one-time correction
branch is available only for a fully attributed SHACL-only dry-run failure; host evidence compares the
new batch and item hashes to prove only finding-attributed instance items changed, then requires its
immediate unchanged apply. Any correction failure stops the run.
The host audit enforces the remaining instance, validation, reasoning, governed-query, session,
checkpoint, completion and final-GET sequence, including the 600-second core and 600–660 terminal-only
window. The sole permitted query warning records the generic absence of a current rule result pointer;
it is retained as an optional-rule-absent decision rather than removed by running a rule.

Each file-spool request ID is one to 64 characters: a lower-case letter followed only by lower-case
letters, digits, `_` or `-`. The matching filename is exactly `<id>.json`; path components, other
characters and overlong names remain rejected before any host forwarding.
