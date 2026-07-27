# M4 isolated modeling contract

You are given only the files listed in `input-manifest.json`, the local clarification response files
created for your own requests, and responses from the generic public platform API spool. No previous
run, answer model, hidden contract, test specification, or host directory is an input.

Use immutable Modeling Batch dry-run followed by `apply_atomic`, with the public platform contract.
Do not write RDF directly, use a semantic-edit bypass, load a dataset, or set `validate=false`.
Retain your question/answer, changed assumption, Batch rationale, validation/reasoning/query evidence
and any explicit gap in an append-only decision log and runtime record.

Business clarification is deliberately separate from platform RPC. A clarification response is a
business decision, not Evidence and not an ontology recipe. The host never chooses Classes,
Properties, IRIs, Shapes, queries, or Batch payloads for you.
