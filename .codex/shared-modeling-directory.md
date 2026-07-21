# Shared Modeling Directory

`.codex/shared_modeling_directory.py` implements the R1.1-006 repo-local collaboration substrate.
It creates current-state files under the already-gitignored
`workspaces/modeling-runs/<run-id>/` tree and provides deterministic validation, merge, review,
Batch planning, materialization, response binding, and verification checks.

This tool is not a Local/Formal Profile runner. It does not choose a Profile, start a Harness,
load credentials, create Build Sessions, acquire Leases, submit a request, refresh Modeling
Context, launch an Agent, or persist clarification messages. R1.1-007 owns those behaviors. A
coordinator or thin acceptance driver supplies non-secret live limits and attempt-size placeholders,
performs platform calls, refreshes Modeling Context, and returns response metadata to this tool.

## Create a run

Create a temporary coordinator-owned bootstrap JSON outside the run directory. Its minimum shape
is:

```json
{
  "run_id": "dify-run-001",
  "repository_root": "/absolute/path/to/ontology-platform",
  "project_ref": {
    "project_id": "project-id",
    "build_session_id": null
  },
  "brief": "Business goal, scope, terms, competency questions, and constraints.",
  "allowed_command_kinds": [
    "create_class",
    "create_relation_type",
    "create_entity",
    "create_relation"
  ],
  "sources": [
    {
      "source_id": "dify-docs",
      "locator": "workspaces/reference-docs/dify/index.md",
      "scope": {"ontology_ids": ["dify"]}
    }
  ],
  "competency_questions": [
    {
      "competency_question_id": "cq-workflow-nodes",
      "ontology_id": "dify",
      "text": "Which nodes belong to a workflow?",
      "acceptance": {"must_return_relation": "hasNode"}
    }
  ],
  "coverage_items": [
    {
      "coverage_id": "workflow-topology",
      "ontology_id": "dify",
      "work_unit_id": "dify-topology",
      "source_ids": ["dify-docs"],
      "competency_question_ids": ["cq-workflow-nodes"],
      "status": "planned"
    }
  ],
  "work_units": [
    {
      "work_unit_id": "dify-topology",
      "ontology_id": "dify",
      "source_ids": ["dify-docs"],
      "coverage_ids": ["workflow-topology"],
      "competency_question_ids": ["cq-workflow-nodes"],
      "dependency_work_unit_ids": [],
      "input_paths": [
        "shared/brief.md",
        "workspaces/reference-docs/dify/index.md"
      ],
      "output_contract": {
        "result_schema": "shared-modeling-result-v1",
        "allowed_command_kinds": [
          "create_class",
          "create_relation_type",
          "create_entity",
          "create_relation"
        ]
      }
    }
  ],
  "ontologies": [{"ontology_id": "dify"}]
}
```

The command computes source hashes and each task input fingerprint. Source locators and ordinary
input paths are repository-relative; `shared/...` and `units/...` paths are run-relative. A source
must declare every Ontology in which it may be used.

```bash
backend/.venv/bin/python .codex/shared_modeling_directory.py init \
  workspaces/modeling-runs/dify-run-001 --spec /tmp/dify-run-001.json

backend/.venv/bin/python .codex/shared_modeling_directory.py inspect \
  workspaces/modeling-runs/dify-run-001

backend/.venv/bin/python .codex/shared_modeling_directory.py validate \
  workspaces/modeling-runs/dify-run-001
```

Do not place API keys, credentials, Lease tokens, passwords, secret fields, hidden reasoning, or a
clarification mailbox in the run. The validator rejects those fields/files. Source indexes store
stable locators and hashes, not copied source bodies.

## Complete and recover a Work Unit

A worker receives only the run path and `work_unit_id`. It reads `run.json`, shared files, its
`task.json`, referenced source paths, and completed direct-dependency results. It writes only its
own `result.json` and `status.json`, using atomic replacement.

A ready result has this shape:

```json
{
  "schema_version": "1.0",
  "work_unit_id": "dify-topology",
  "ontology_id": "dify",
  "input_fingerprint": "hash copied from the current task",
  "source_ids": ["dify-docs"],
  "coverage_ids": ["workflow-topology"],
  "competency_question_ids": ["cq-workflow-nodes"],
  "modeling_items": [
    {
      "client_item_id": "workflow-entity",
      "command_kind": "create_entity",
      "payload": {"name": "Example workflow"},
      "depends_on": [],
      "evidence_reference_ids": [],
      "evidence": [
        {"document_name": "index.md", "excerpt": "Exact bounded source excerpt"}
      ],
      "rationale": "Answers cq-workflow-nodes",
      "competency_question_ids": ["cq-workflow-nodes"]
    }
  ],
  "gaps": [],
  "summary": "Bounded worker result"
}
```

Set the matching status to `ready` only after the result is complete. A fresh worker can continue
from the same files without chat recovery. An incomplete direct dependency blocks a ready result
and Ontology merge.

Reset only a specifically inspected failed or stale unit:

```bash
backend/.venv/bin/python .codex/shared_modeling_directory.py reset-unit \
  workspaces/modeling-runs/dify-run-001 dify-topology
```

This removes that unit's result, refreshes its task fingerprint, and returns it to `pending`; it
does not alter unrelated units.

When an R1.1-007 coordinator receives an explicit `no_change` assessment, pass the complete
assessed result. The tool compares normalized modeling items and gaps with the current result,
rejects any semantic change, records a bounded reason, and rebinds only the input fingerprint:

```bash
backend/.venv/bin/python .codex/shared_modeling_directory.py rebind-no-change \
  workspaces/modeling-runs/dify-run-001 dify-topology \
  --assessment /tmp/dify-topology-assessed-result.json \
  --reason "Editorial source change; normalized semantic items and gaps are unchanged."
```

`modify_existing` and `remodel` are not rebind operations: the worker writes a newly modeled result.

## Merge, review, and plan

Merge all ready/accepted units for one Ontology:

```bash
backend/.venv/bin/python .codex/shared_modeling_directory.py merge \
  workspaces/modeling-runs/dify-run-001 dify
```

Merge rejects duplicate item IDs, cycles, unresolved item references, conflicting semantic
identities, conflicting shared terminology, stale inputs, and incomplete dependencies. It
topologically orders items with `client_item_id` as the tie-break. The candidate hash covers only
the Ontology ID, stable contributor IDs, and normalized semantic items. Input fingerprints,
timestamps, review state, and transport attempts cannot change that hash.

An independent reviewer writes `ontologies/dify/review.json`:

```json
{
  "schema_version": "1.0",
  "ontology_id": "dify",
  "candidate_hash": "current candidate hash",
  "verdict": "PASS",
  "findings": []
}
```

Planning refuses `REVISE`, `BLOCKED`, or a stale review. Supply exactly the four current capacity
limits and both request-shape templates. `lease_token_chars` models only the serialized length; no
Lease token value is accepted or persisted.

```json
{
  "modeling_batch_max_items": 100,
  "modeling_batch_max_request_bytes": 1048576,
  "modeling_batch_max_inline_evidence": 100,
  "modeling_batch_max_evidence_excerpt_chars": 20000
}
```

```json
[
  {
    "mode": "dry_run",
    "idempotency_key": "bounded-dry-attempt-placeholder",
    "expected_workspace_version": "workspace-version-placeholder",
    "lease_token_chars": 0
  },
  {
    "mode": "apply_atomic",
    "idempotency_key": "bounded-apply-attempt-placeholder",
    "expected_workspace_version": "workspace-version-placeholder",
    "lease_token_chars": 128
  }
]
```

```bash
backend/.venv/bin/python .codex/shared_modeling_directory.py plan \
  workspaces/modeling-runs/dify-run-001 dify \
  --limits /tmp/live-modeling-limits.json \
  --attempts /tmp/request-size-templates.json
```

Planning is deterministic and splits on item count, serialized request bytes, or total inline
Evidence count. One overlong excerpt or single item that cannot fit is blocked before submission.

## Materialize and bind platform responses

Logical dependencies may cross Batches, but submitted references may not. Process Batches in plan
order. Materialization requires each predecessor to be applied and Modeling Context to have been
refreshed. It replaces cross-Batch `{item_ref: ...}` objects with returned stable resource IDs/IRIs
and removes cross-Batch `depends_on`; same-Batch references remain for the platform compiler.

```bash
backend/.venv/bin/python .codex/shared_modeling_directory.py materialize \
  workspaces/modeling-runs/dify-run-001 dify <client-batch-id> \
  --attempts /tmp/actual-request-size-templates.json
```

The output fixes `client_batch_id`, normalized items, exact request byte counts, and an
immutable-content hash over `{ontology_id, items}`. Attempt mode, workspace version, Lease-token
length, and idempotency key do not affect that identity. If concrete stable references make an
unsubmitted multi-item request exceed the byte limit, materialization deterministically replaces
it with smaller logical partitions and returns the first replacement ID. An already dry-run or
applied Batch is never changed.

The external driver serializes and sends the real envelope, then records its response metadata:

```bash
backend/.venv/bin/python .codex/shared_modeling_directory.py bind-response \
  workspaces/modeling-runs/dify-run-001 dify <client-batch-id> dry_run \
  <immutable-content-hash> --response /tmp/dry-run-response.json

backend/.venv/bin/python .codex/shared_modeling_directory.py bind-response \
  workspaces/modeling-runs/dify-run-001 dify <client-batch-id> apply_atomic \
  <immutable-content-hash> --response /tmp/apply-response.json --context-refreshed
```

The dry-run response must be `validated`. Apply must reuse the same `client_batch_id`, immutable
content, and returned platform `batch_id`, but uses a new external Attempt/idempotency identity.
Apply item results must include their stable `resource_outputs` so later Batches can materialize.
If a later Batch fails, already applied entries stay `applied`; the tool makes no cross-Batch
rollback claim.

## Record retrieval verification

After every Batch is applied, the coordinator executes the pre-recorded competency questions and
semantic-retrieval checks against platform current state and writes the indexed
`verification.json`:

```json
{
  "schema_version": "1.0",
  "ontology_id": "dify",
  "candidate_hash": "current candidate hash",
  "batches": [
    {
      "client_batch_id": "planned client batch ID",
      "platform_batch_id": "bound platform batch ID",
      "immutable_content_hash": "materialized content hash"
    }
  ],
  "checks": [
    {
      "competency_question_id": "cq-workflow-nodes",
      "status": "passed",
      "query": "Recorded Context Query or SPARQL check",
      "returned_resources": ["stable-resource-id"]
    }
  ],
  "gaps": [],
  "verdict": "PASS"
}
```

```bash
backend/.venv/bin/python .codex/shared_modeling_directory.py validate-verification \
  workspaces/modeling-runs/dify-run-001 dify
```

`PASS` requires an applied complete plan, exact candidate/Batch identities, coverage of every
Ontology competency question, and only passing checks. Every passed check must include a bounded,
non-empty `query` or `check_description` plus structured observed-result evidence. Normally that is
a non-empty list in `returned_resources`, `returned_relations`, `returned_evidence`, `rows`, or
`matches`. A competency question that correctly expects no result may instead use an empty result
list and this explicit assertion:

```json
{
  "empty_result": {
    "expected": true,
    "observed_count": 0,
    "assertion": "Why an empty observed result satisfies this competency question."
  }
}
```

Missing descriptions, scalar/malformed result fields, unexplained empty lists, contradictory
non-empty/empty evidence, and malformed empty assertions are rejected. File completeness or
successful dry-run alone is not retrieval acceptance.
