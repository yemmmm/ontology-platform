# M2 rehearsal log (append-only)

No live M2 run has been performed by this package author.

Append one entry per execution with the run tag, project/ontology/build-session
IDs, mode probes, Evidence IDs, batch/attempt IDs and statuses, bad-candidate
finding code/path, Graph Set `shapes` member, validation/reasoning run IDs,
scoped-query assertions, verifier result, and any blocker.  Do not record API
keys, lease tokens, cookies, Authorization headers, or full raw requests.

## 2026-07-24T08:32:12.882653+00:00 — 0d952d8711d7 (failed)
- Last stage: `draft-fixture`.
- Project/Ontology/Build Session: `eca27355-177d-45ab-a8d0-bb27573ab242` / `458c1939-0c13-4f35-a34f-4470199dbc4f` / `c1ac6d1a-7395-4826-9256-1036c85850cb`.
- Safe partial runtime record retained at `runtime/runtime-record.json`; no credentials or lease tokens were recorded.

## 2026-07-24T08:36:59.765985+00:00 — 2fde5cd4f165
- Project/Ontology/Build Session: `94dcff15-dc45-40d3-b85f-b9318d96aef6` / `a093b881-f2ad-4fc9-aaa5-541e77a01992` / `f17db96f-c78f-4fbd-9089-b66899458469`
- Modes: regular expected `legacy_only`; isolated observed `rdf_primary`.
- Bad Shape: `validation_failed`; invalid Invocation: `validation_failed`.
- Validation/reasoning: `9225a4fc-d693-45b0-b5f8-473c1721c2a0` / `37bc96ef-de33-4856-962c-46d27b84b32d`; Graph Set shapes member `http://ontology-platform.local/semantic/graph/shapes/a093b881-f2ad-4fc9-aaa5-541e77a01992`.
- Runtime record: `runtime/runtime-record.json`; secrets deliberately excluded.
- Corrects prior run: `0d952d8711d7`.

## 2026-07-24T08:45:29+00:00 — independent acceptance correction

- The opening “No live M2 run” sentence records the package author's initial state and is superseded
  by the two live entries above.
- Independent acceptance re-read both retained Projects, reproduced the invalid Invocation
  `shacl_violation` without apply, repeated all scoped queries, and passed M1 13/13, M2 5/5 and
  focused backend 69/69 tests.
- Final M2 result: PASS. The isolated runtime is stopped by the delivery owner after acceptance;
  both owned Projects remain retained for traceability and M3 handoff.
