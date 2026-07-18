# Phase 2 Semantic Namespace, Mapping, and Export Baseline

> **Note (2026-07-08):** The `op:FactClaim` reified-assertion projection and
> the `op:evidenceStatus "missing_evidence"` export marker described below
> have been removed. Evidence bindings now live in the Postgres
> `fact_evidence_bindings` table at `fact_id` granularity. See
> `docs/delivery/designs/2026-07-08-evidence-postgres-refactor-design.md`.
> Other Phase 2 namespace and export conventions remain in force.

## Status

Implemented as a read-only export baseline. Existing product writes still use the current
Postgres/Neo4j-backed model. This phase proves that the current business-visible ontology and graph
state can be represented as RDF/OWL/SKOS/SHACL before canonical RDF writes are introduced.

## Namespace and IRI Conventions

The backend derives semantic IRIs from `Settings.semantic_base_iri` and
`Settings.semantic_graph_iri_prefix`. The default base is:

```text
http://ontology-platform.local/semantic/
```

Stable resource patterns:

- `project/{project_id}`
- `ontology/{ontology_id}`
- `version/{version_id}`
- `class/{class_id}`
- `property/{property_id}`
- `relation-type/{relation_type_id}`
- `entity/{entity_id}`
- `relation/{relation_id}`
- `fact-claim/{fact_claim_id}`
- `evidence/{evidence_id}`

Stable graph patterns:

- `graph/ontology/{ontology_id}` for schema terms.
- `graph/data/{ontology_id}` for entity, relation, and fact-claim assertions.
- `graph/shapes/{ontology_id}` for generated SHACL shapes.
- `graph/evidence/{project_id}` for evidence records.

These IRIs are computed from existing IDs in Phase 2. They are not persisted into the legacy tables
and do not change existing write behavior.

## Mapping

Schema export maps current ontology objects into standards-compatible terms:

- Ontologies become `owl:Ontology`.
- Classes become `owl:Class` with `rdfs:label`, `rdfs:comment`, `skos:altLabel`, and
  `rdfs:subClassOf`.
- Properties become `owl:DatatypeProperty` or `owl:ObjectProperty` with domain/range metadata.
- Enum values become `skos:Concept` resources.
- Relation types become `owl:ObjectProperty`, including domain/range, scope policy, status, and
  symmetric/transitive typing where applicable.
- External HTTP/HTTPS/URN mappings are emitted as `owl:sameAs`.

Data export maps current graph and governance objects:

- Entities become `op:Entity` and are also typed by their class IRI.
- Entity properties are emitted through the generated property IRIs.
- Relations are represented both as direct entity-to-entity object-property triples and as
  reified `op:Relation` resources with source, target, type, status, and IDs.
- Fact claims become `op:FactClaim` resources with predicate, value, confidence, audit status,
  generation reason, stale state, and evidence links.
- Fact claims with no `evidence_ids` are explicitly marked as `op:evidenceStatus
  "missing_evidence"` and `op:missingEvidence true`.
- Evidence rows become `prov:Entity` plus `op:Evidence`.

## API Surface

Read-only Phase 2 endpoints:

- `GET /api/semantic/namespaces`
  returns the JSON-LD context and IRI pattern manifest.
- `GET /api/ontologies/{ontology_id}/semantic-export?format=trig|turtle|json-ld`
  exports current schema, data, fact claims, and evidence.
- `GET /api/ontologies/{ontology_id}/semantic-shapes?format=trig|turtle|json-ld`
  exports generated SHACL shapes.
- `POST /api/semantic/projections:parse`
  parses a semantic export and returns a compact business JSON projection for parity tests.

## SHACL Generation

Generated SHACL shapes express the current structural constraints used by product screens:

- Required properties use `sh:minCount 1`.
- Single-valued properties use `sh:maxCount 1`.
- Scalar property types map to XSD datatypes.
- Enum properties use `sh:in`.
- Relation type source/target constraints are emitted as class/path property shapes where practical.

## Verification

Backend tests cover:

- deterministic namespace/context generation,
- RDF export parseability and key OWL/SKOS/PROV-O triples,
- explicit missing-evidence representation,
- generated SHACL constraints,
- RDF export to compact business JSON round-trip projection,
- API media types and projection parse behavior.

Run:

```bash
cd backend && uv run pytest
```
