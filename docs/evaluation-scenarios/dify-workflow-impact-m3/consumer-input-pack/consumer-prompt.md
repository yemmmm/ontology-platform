# Independent read-only consumer task

You are a fresh, independent consumer Agent. Your only mounted inputs are
`/opt/consumer-prompt.md`, `/opt/consumer-read-query-contract.md`,
`/opt/consumer-request.json`, and `/opt/m3_readonly_rpc.py`. Read the contract and request from
those exact `/opt/` paths; the request contains a business question plus the target Project and
Ontology IDs. You do not receive any producer brief, rationale, model
transcript, M1/M2 material, prior answer, local memory, credential or writable platform channel.

Use `/opt/m3_readonly_rpc.py` for every platform call; it is the only supported way to create a
request and receipt. It writes the exact file-spool request safely and prints the complete response
envelope. You may read the allowlisted generic semantic context endpoints and submit scoped SPARQL
queries. You must not create, update, delete, validate, reason, model, acquire a lease, or call any
other platform write operation. If the question cannot be answered from the returned facts, state the
gap rather than guessing.

For every complete response you read, the client appends one canonical receipt to
`/mnt/spool-consumption-receipts.jsonl` with exactly the receipt schema used by the producer:
`run_tag`, `request_id`, `response_id`, `canonical_request_sha256`, `host_response_sha256`, `status`,
and `response_read_confirmed`. `run_tag` must equal the launcher-injected `M3_RUN_TAG`. Compute the
request hash from the canonical request bytes and the response hash from the raw read-only response
bytes. Record every well-formed status, including a non-2xx response.

After all reads, run `/opt/m3_readonly_rpc.py --finalize-runtime-record`. It writes
`/mnt/runtime-record.json` with `run_tag`, `spool_receipt_log` exactly equal to
`{"path":"spool-consumption-receipts.jsonl","sha256":"<sha256>","count":<n>}`, and the full
ordered `spool_receipts` mirror from the receipt log. Do not replace `spool_receipt_log` with a string
path or alter any receipt. End your final message with exactly these two lines, in this order. The
first is the consumer's own terminal outcome: use `CONSUMER_READY` only when you completed the
read-only investigation and fact-attributed answer; use `BLOCKED` for a declared answerable-contract
blocker; otherwise use `INCONCLUSIVE`. The second line copies the helper's exact output:

```text
CONSUMER_RESULT <CONSUMER_READY|BLOCKED|INCONCLUSIVE>
M3_RECEIPT_SUMMARY run_tag=<M3_RUN_TAG> receipt_count=<n> receipt_log_sha256=<sha256>
```

Return a fact-attributed answer for the business question. Separate platform-returned source facts,
synthetic facts, inferences and your own judgment. Do not assign an impact/risk level.
