# Proposal formats

Every proposal envelope contains:

```json
{
  "project_id": "project-id",
  "ontology_id": "ontology-id",
  "target_version_id": "draft-version-id",
  "proposal_type": "schema_change",
  "source_type": "agent",
  "idempotency_key": "stable-run-and-batch-key",
  "payload": {"items": []},
  "created_by_type": "agent",
  "created_by": "agent-id",
  "model_identifier": "model-id",
  "prompt_version": "ontology-builder/v0.4",
  "evidence": []
}
```

Each item has a stable `key`, `kind`, structured `data`, and `confidence`. While creating a proposal,
bind items to entries in the envelope's `evidence` array with `evidence_indexes`. If
`evidence_indexes` is omitted, the platform binds every envelope Evidence record to the item. The
platform replaces this creation-only field with durable `evidence_ids`; clients must not invent those
IDs.

For document Evidence, first call `get_source_document_chunks`. Use the returned `document_id`, chunk
`id`, `page_number`, absolute `char_start`/`char_end`, exact `text` slice, and chunk `content_hash`.
Validation requires both of these equalities:

```text
quote == chunk.text[char_start - chunk.char_start : char_end - chunk.char_start]
content_hash == chunk.content_hash
```

Do not replace line breaks, normalize whitespace, change quotation marks, or use a document-level hash.

## Entity example

```json
{
  "project_id": "project-id",
  "ontology_id": "ontology-id",
  "target_version_id": "draft-version-id",
  "proposal_type": "entity",
  "source_type": "agent",
  "idempotency_key": "source-hash:entities:001",
  "payload": {
    "items": [
      {
        "key": "entity:customer:c001",
        "kind": "entity",
        "confidence": 0.98,
        "evidence_indexes": [0],
        "data": {
          "class_id": "customer-class-id",
          "name": "Example Customer",
          "aliases": [],
          "properties": {"customerCode": "C001"}
        }
      }
    ]
  },
  "created_by_type": "agent",
  "created_by": "agent-id",
  "model_identifier": "model-id",
  "prompt_version": "ontology-builder/v0.4",
  "evidence": [
    {
      "source_type": "document",
      "document_id": "document-id",
      "page_number": null,
      "chunk_id": "chunk-id",
      "char_start": 10,
      "char_end": 26,
      "quote": "Example Customer",
      "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  ]
}
```

Relation proposals use the same envelope and Evidence rules. Each relation item contains a reviewed
`relation_type_id`, `source_entity_id`, `target_entity_id`, and optional relation `properties`.

If a provider cannot serialize the nested `proposal` argument, encode this entire envelope as one JSON
string and call `submit_proposal_json`; do not reshape or relocate its fields.

Schema item kinds are `class`, `property`, `relation_type`, and `constraint`. Entity items include a
reviewed `class_id`, canonical `name`, aliases, and properties. Relation items may represent schema-
allowed edges or entity-level instance facts when their reviewed relation type permits it. Merge items
identify both entity IDs and evidence supporting identity equivalence.

## v0.4 proposal kinds

`mapping` proposals describe Semantic Mapping. Each item should identify the ontology object or entity,
external system, external resource, external field, identifier type, join key, validity window, owner,
and confidence. Use this for facts such as `AssessmentResult.score` being stored in an external grade
system.

`catalog` proposals describe Data Catalog entries. Each item should identify data source, resource,
field, authoritative status, freshness, sensitivity, access policy, masking rule, approval instruction,
and audit requirement. Use this for fields such as `student_pii.id_card_number` that must not be stored
as graph properties.

`entity_relation` proposals describe instance-specific relations that do not change ontology schema.
Each item should include `relation_type_id`, `source_entity_id`, `target_entity_id`, `scope=instance`,
status, validity window, and relation properties. Use this for facts such as
`entity1 --CONFLICTS_WITH--> entity2`.

Build idempotency keys from stable inputs such as project, version, source content hash, extraction stage,
and deterministic batch number. Retrying the same logical batch must reuse its key. Changed content or a
deliberately revised batch must use a new key.
