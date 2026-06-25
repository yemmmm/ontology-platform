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

For artifact Evidence, first call `get_evidence_artifact_chunks`. Use the returned `artifact_id`,
compatibility `document_id`, chunk `id`, `page_number`, absolute `char_start`/`char_end`, exact
`text` slice, and chunk `content_hash`.
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
      "artifact_id": "artifact-id",
      "document_id": "artifact-id",
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

## v0.4 modeling outside the proposal envelope

v0.4 does not introduce new `proposal_type` values. Semantic Mapping, Data Catalog, and Connector
configuration are managed as first-class project resources through dedicated MCP tools and HTTP
endpoints, separate from the governance proposal queue.

- **Semantic Mapping** (ontology object ↔ external field): use the `create_semantic_mapping` MCP
  tool (or `POST /api/projects/{project_id}/semantic-mappings`). Include `ontology_id`,
  `target_type` (`class` / `property` / `relation_type` / `entity`), `target_id`, `field_id`,
  `join_key`, validity window, `confidence`, and `owner`. Use this for facts such as
  `AssessmentResult.score` being stored in an external grade system. Update with
  `update_semantic_mapping` (renaming the underlying resource or field auto-propagates).
- **Data Catalog** (source, resource, field sensitivity, access policy): use `create_data_source`,
  `create_data_resource`, and `create_external_field`. Each field records `sensitivity`
  (`public` / `internal` / `confidential` / `restricted`), `access_policy`
  (`allow` / `mask` / `approval_required` / `deny`), masking rule, and audit requirement. Use this
  for fields such as `student_pii.id_card_number` that must not enter the graph.
- **Instance-scoped entity relations** (no schema change): use `propose_relations` with the existing
  `relation` proposal type, but mark each item's `data` with `scope: "instance"`, optional
  `valid_from` / `valid_to`, and `status`. Use this for facts such as
  `entity1 --CONFLICTS_WITH--> entity2` when the RelationType is marked `entity_only` or `both`.
- **Governed connector queries**: use `run_connector_query` after defining a template with
  `create_connector_template`. The platform records an audit row and applies field-level masking
  and approval policies before returning data.

Build idempotency keys for proposals (schema/entity/relation/merge) from stable inputs such as
project, version, artifact content hash, extraction stage, and deterministic batch number. Retrying
the same logical batch must reuse its key. Changed content or a deliberately revised batch must use
a new key.

The legacy MCP tools `get_source_document_status` and `get_source_document_chunks` remain
compatibility aliases. Prefer the evidence artifact tool names in new traces.
