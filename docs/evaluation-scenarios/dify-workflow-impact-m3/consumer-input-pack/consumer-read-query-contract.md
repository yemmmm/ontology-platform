# Generic read/query contract for the independent consumer

The consumer gateway permits only these public operations:

- `GET /openapi.json`
- `GET /api/health`
- `GET /api/projects/{project_id}/build-context`
- `GET /api/ontologies/{ontology_id}/modeling-context`
- `GET /api/ontologies/{ontology_id}/semantic-read-models/...`
- `POST /api/semantic/sparql:query`

Use the mounted `/opt/m3_readonly_rpc.py` client for every operation. Its executable contract is:

- Request is exactly `{"id","method","path","headers","body"}` in canonical compact JSON.
  `id` must match `^[a-z][a-z0-9_-]{7,63}$`; its request filename is exactly `<id>.json`.
- The client writes an unscanned temporary file outside `M3_API_REQUEST_DIR`, then atomically places
  only the final `<id>.json` in that directory. Do not create any request file by hand.
- The host response is exactly `{"id","status","headers","body"}` at
  `M3_API_RESPONSE_DIR/<id>.json`. The client verifies the matching ID and integer status before it
  prints the complete response envelope.
- The client appends exactly one canonical receipt per read response with fields `run_tag`,
  `request_id`, `response_id`, `canonical_request_sha256`, `host_response_sha256`, `status`, and
  `response_read_confirmed`. It has no platform credential and does not write response files.
- Run `/opt/m3_readonly_rpc.py --finalize-runtime-record` once after all reads. It writes the only
  accepted runtime receipt evidence: `spool_receipt_log` is the object
  `{"path":"spool-consumption-receipts.jsonl","sha256":"<sha256>","count":<n>}`, and
  `spool_receipts` is the exact ordered JSONL mirror. Its output is the required transcript summary.

The caller supplies the Project ID, Ontology ID and business question. Query text and any answer
criteria are chosen by the consumer or independent tester; this contract contains no domain ontology,
reference answer, fixture, expected row or impact judgment. Every response must be read through the
file-spool receipt protocol. No write or lifecycle endpoint is permitted.
