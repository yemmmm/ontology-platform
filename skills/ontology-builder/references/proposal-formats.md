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
  "prompt_version": "ontology-builder/v0.3",
  "evidence": []
}
```

Each item has a stable `key`, `kind`, structured `data`, `confidence`, and `evidence_ids`. Evidence in the
envelope contains `source_type`, optional `document_id`, `page_number` or character offsets, optional
`chunk_id`, exact `quote`, and a 64-character `content_hash`.

Schema item kinds are `class`, `property`, `relation_type`, and `constraint`. Entity items include a
reviewed `class_id`, canonical `name`, aliases, and properties. Relation items include a reviewed
`relation_type_id`, source/target entity IDs, and relation properties. Merge items identify both entity
IDs and evidence supporting identity equivalence.

Build idempotency keys from stable inputs such as project, version, source content hash, extraction stage,
and deterministic batch number. Retrying the same logical batch must reuse its key. Changed content or a
deliberately revised batch must use a new key.
