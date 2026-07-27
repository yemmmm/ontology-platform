# M4 blind read-only consumer

You are a fresh, read-only consumer. You have no modeling-agent decision log, hidden answer contract,
fixture answer, mutation specification, credential, or prior run state. Use only the public API through
the injected M4 API file spool to inspect the supplied Project/Ontology scope and answer the provided
consumer task from modeled facts, Evidence/provenance, inference and explicit gaps.

`/opt/consumer-scope.json` is the only supplied scope input. It contains exactly `project_id`,
`ontology_id`, and `graph_set_id`; do not discover, list, substitute, or broaden those IDs. The API
spool permits only bodyless `GET` requests within that scope. Every request is canonical compact UTF-8
JSON, stored as lowercase `<id>.json` where `id` matches `[a-z][a-z0-9_-]{0,63}` and has exactly this
envelope:

```json
{"body":null,"headers":{},"id":"<lowercase-id>","method":"GET","path":"/api/..."}
```

First, make one canonical bodyless `GET` to
`/api/ontologies/<ontology_id>/modeling-context`, substituting only the supplied `ontology_id`. Read and
verify its matching response file. From that response, use only the exact REST URLs in
`query_entries.entities.rest` and `query_entries.facts.rest`, preserving every returned path and query
parameter verbatim. Do not invent shorter paths, guess endpoints, or make any later API request outside
those two returned read-model URLs.

Read only your matching files from `M4_API_RESPONSE_DIR`, verify every SHA-256, and do not write, infer,
or use a fallback from silence. Write `/mnt/consumer-record.json` with exactly these five top-level keys:
`terminal_status`, `scope`, `receipts`, `observations`, and `claim_classifications`. `scope` must exactly
match the supplied scope. `receipts`, `observations`, and `claim_classifications` must each have exactly
these answer-neutral slots: `current_target_contract`, `output_continuity`, and `missing_score`.

Each receipt binds that observation to a successful semantic-read-model request using its host-audited
`request_id`, `canonical_request_sha256`, and `response_sha256`; metadata or modeling-context receipts do
not count. Each observation must record actual non-empty modeled conclusions. Use
`current_target`, `target_version`, and `b_contract` for `current_target_contract`; use
`old_contract_change`, `new_contract_change`, and `continuity` for `output_continuity`; and use
`{"state":"unknown","explicit_gap_observed":true,"gap":"<non-empty modeled gap>"}` for
`missing_score`. Do not invent a missing-score policy. Classify each slot as `source`, `synthetic`,
`inference`, or `judgment`. End with `CONSUMER_READY`, `BLOCKED`, or `INCONCLUSIVE`.
