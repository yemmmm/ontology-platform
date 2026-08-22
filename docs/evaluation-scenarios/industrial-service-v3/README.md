# Industrial service v3 scenario baseline

This directory contains the preparation baseline for the v3.0 industrial equipment after-sales
service scenario. It is a fixture for a future modeling and ontology-guided SQL experiment; it is
not a product migration and it does not contain RDF business-row instances.

## Information boundary

The future modeling runtime may mount only the four files listed in
`modeling-input/input-manifest.json`: a short scenario brief, a short term list, the relational
schema, and representative sample data. The full process truth, fixed query answers, schema
contract, and verification queries live outside that allowlist or under `verification/` and are
tester-only material. This repository layout is a classification boundary for this preparation
phase, not an OS sandbox; runtime path isolation is a later R3.0-006 acceptance item.

## PostgreSQL fixture

Use the repository-root loader below to recreate the dedicated `industrial_service_v3` schema in
the existing Compose PostgreSQL service:

```bash
./scripts/load-industrial-service-v3-postgres.sh
```

The loader reads the existing container `POSTGRES_USER` and `POSTGRES_DB`, uses no printed password,
checks the fixture owner/comment marker before any drop, and preserves a sentinel of non-target
relations. It is intentionally not an SQL adapter and implements no semantic or business-data
authorization.

The schema and seed files set an explicit `search_path`, use deterministic IDs/timestamps, and are
the sole source used both for modeling input and database loading. PostgreSQL remains the only
business-fact store in this baseline; the ontology work in a later phase will describe semantics
and mappings only.
