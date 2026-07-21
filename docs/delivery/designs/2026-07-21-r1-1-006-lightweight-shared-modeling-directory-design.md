# R1.1-006 轻量共享建模目录与分片协作设计

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-006
- Status: plan review PASS; implementation pending
- Priority: modeling quality and retrieval quality first

## Goal

Let multiple local Agent sessions share complete task information and work on bounded modeling
units without requiring the main Agent to copy large context through prompts. Keep the implementation
small enough that a developer can inspect files, edit one unit, and rerun only the affected work.

## Current minimal scope

All participants run on one development machine against the same repository checkout. A gitignored
directory under `workspaces/modeling-runs/<run-id>/` stores current collaboration state. The platform
continues to own applied semantic state, Modeling Batch dry-run/apply, and retrieval results, but it
does not store every intermediate collaboration step in this mode.

The initial implementation needs only:

1. one small launcher/initializer that creates and validates the directory skeleton;
2. human-readable Markdown for the business brief and JSON for indexes, tasks, status, results, and
   optional reviews;
3. one coordinator writer for shared files and one assigned writer for each Work Unit directory;
4. atomic JSON replacement so another Agent never reads a partially written file;
5. commands to initialize, inspect, validate, and reset a specifically named Work Unit.

No background service, database migration, API, event recorder, dynamic scheduler, or generic file
store is required.

## Directory contract

```text
workspaces/modeling-runs/<run-id>/
  run.json
  shared/
    brief.md
    source-index.json
    coverage.json
  units/
    <work-unit-id>/
      task.json
      status.json
      result.json        # absent until produced
  ontologies/
    <ontology-id>/
      candidate.json     # the single merged candidate for this Ontology
      review.json        # independent review bound to candidate hash
      batch-plan.json    # ordered platform-sized batches bound to candidate hash
      verification.json  # post-apply competency-question and retrieval results
```

`run.json` records stable local identifiers and platform IDs needed for final dry-run/apply. It must
not contain credentials. `task.json` is self-contained except for stable relative paths into
`shared/`, the fixed source corpus, and completed dependency units. The main Agent launches a worker
with only the run directory and Work Unit ID.

### Minimum data contract

This is a small closed contract for the experiment, not a generic metadata framework. The first
implementation validates at least these fields and rejects unknown references:

| File | Required content |
| --- | --- |
| `run.json` | `schema_version`, `run_id`, `project_id`, `build_session_id`, paths for brief/source index/coverage, indexed Work Units (`work_unit_id`, `ontology_id`, task/status/result paths), and indexed Ontology candidate/review/batch-plan/verification paths |
| `source-index.json` | `sources[]` with unique `source_id`, stable `locator`, declared scope, and current `content_hash` |
| `coverage.json` | `competency_questions[]` with ID/text/acceptance and `items[]` with unique `coverage_id`, `source_ids`, `competency_question_ids`, `ontology_id`, `work_unit_id`, and current status |
| `task.json` | `schema_version`, `work_unit_id`, `ontology_id`, `source_ids`, `coverage_ids`, `competency_question_ids`, `dependency_work_unit_ids`, stable input paths, `input_fingerprint`, and an `output_contract` naming the result schema and allowed command kinds |
| `result.json` | matching schema/unit/Ontology/input fingerprint and source/coverage/question IDs, `modeling_items`, explicit `gaps`, and a short summary |

`modeling_items` use the existing platform `ModelingItemInput` shape: stable `client_item_id`,
`command_kind`, `payload`, `depends_on`, evidence references or inline evidence, rationale, and
competency-question IDs. Allowed command kinds are loaded from the current platform compiler rather
than copied into a second permanent list. The first quality run must exercise at least
`create_entity` and `create_relation`, as well as the schema commands those instances require.

The validator resolves every source, coverage, competency-question, dependency, path, and output
contract reference and checks that it belongs to the declared Ontology/Work Unit scope. The
`input_fingerprint` is a hash of the referenced current inputs; it detects an edited brief/task or
source file and forces only the affected result to be rerun. It is a stale-input guard, not a
version history.

Hashes use one small deterministic rule: SHA-256 over UTF-8 JSON serialized with sorted object keys,
compact separators, and list order preserved; raw Markdown/source files use their byte-level
SHA-256. An input fingerprint hashes a path-sorted list of relative path plus content hash. Candidate
items are topologically ordered with `client_item_id` as the tie-break before hashing. This rule is
implemented once in the local helper and covered by repeatability tests.

`status.json` is mutable current state rather than an audit log. First-version transitions are
`pending -> working -> ready | blocked -> accepted`. The coordinator may reset a named failed or
stale unit after inspecting its files. There is no automatic lease, TTL, epoch, or event replay.

## Roles and writes

- The main Agent creates the run, owns `run.json` and `shared/`, assigns Work Units, merges results,
  invokes platform dry-run/apply, and runs retrieval acceptance.
- A modeling Agent reads shared files and its dependencies, then writes only its assigned unit's
  `status.json` and `result.json`.
- A reviewer reads the same shared state plus `candidate.json` and writes the Ontology
  `review.json`. It does not need Workflow Artifact or Event persistence in fast local mode.
- Human debugging may directly correct brief, coverage, or one task file and rerun the affected
  unit. The initializer/validator reports malformed or missing files clearly.

Different Ontologies may be modeled in parallel. Same-Ontology parallelism is disabled by default;
the coordinator may enable it only for explicitly disjoint coverage scopes and must merge before
dry-run.

### Stable Ontology candidate and platform batches

The coordinator merges accepted unit results into one `candidate.json` per Ontology. It contains
the Ontology ID, contributing Work Unit IDs, deterministic ordered modeling items, and
`candidate_hash`. The hash covers the canonical JSON form of the semantic content and contributors,
excluding the hash field itself.

`review.json` records `candidate_hash`, verdict, and findings. `batch-plan.json` records the same
hash and the exact ordered Batch membership. Any semantic change to `candidate.json` invalidates
both files and requires regeneration plus one new review; overwriting the current files is enough,
and no immutable history is required. Dry-run/apply refuses a hash mismatch.

The Batch planner loads the active `modeling_batch_max_items` and
`modeling_batch_max_request_bytes` settings, topologically orders items, and deterministically
partitions the candidate. It serializes the real `ModelingBatchSubmit` envelope before submission;
an oversized batch is split again rather than sent. `depends_on` remains batch-local. Cross-Batch
dependencies are represented by stable semantic resource IDs plus an ordered Batch dependency in
the plan: the predecessor is dry-run/applied first, Modeling Context is refreshed, and then the
dependent Batch is dry-run/applied. A reference that cannot be resolved this way blocks the plan
instead of being guessed.

## Quality-preserving workflow

1. Freeze or identify the source corpus used by the run.
2. Write one concise business brief, competency questions, source index, and coverage map.
3. Split work by Ontology and bounded coverage scope.
4. Launch fresh workers with directory path plus Work Unit ID only.
5. Validate result shape and references; merge one stable candidate per Ontology.
6. Run one independent semantic review bound to the candidate hash.
7. Deterministically split the reviewed candidate into ordered Batches within the live capacity
   limits.
8. For each Batch, verify the candidate hash and actual request size, dry-run, apply, refresh
   Modeling Context, and return Findings only to affected units.
9. Execute recorded competency questions and semantic retrieval checks; update coverage based on
   actual results.

The fast path may skip Modeling Workflow Artifacts, Execution Events, Checkpoints, Harness strict
activation, automatic summaries, lineage inspection, and retrospective publication. A particular
quality investigation may still opt into any existing capability when it provides useful evidence.

## Failures

- Missing or invalid shared input: mark the unit `blocked`; do not infer the missing content.
- Stale input fingerprint: invalidate only results that reference the changed input.
- Incomplete dependency: keep the dependent unit `pending` or `blocked`.
- Malformed result: report the schema error and rerun only that unit.
- Cross-unit semantic conflict: resolve during Ontology merge before dry-run.
- Candidate/review/Batch hash mismatch: stop and regenerate current review or Batch plan.
- Oversized candidate: split into deterministic ordered Batches; an unresolved cross-Batch
  reference blocks before submission.
- Later Batch failure: retain the already applied valid prefix, record the current failed Batch,
  fix or regenerate from platform current state, and run final retrieval acceptance only after the
  complete plan succeeds. The local fast path does not promise cross-Batch atomic rollback.
- Platform Finding: map it back to affected units and rerun only those units.
- Worker loss: start a fresh Agent against the same unit files; no chat recovery is required.

## Future productization

The following are intentionally deferred: server-hosted collaboration storage, cross-machine
synchronization, immutable versions, event/audit history, participant authentication, role-scoped
credentials, dynamic claims, TTL/fencing, automatic crash recovery, distributed scheduling,
conflict-free merge, UI, retention policy, and formal export/import.

If later evidence justifies those capabilities, preserve the Work Unit task boundary, stable input
references, result contract, and quality gates. Do not make the local experiment wait for them.

## Acceptance

- At least two independent Agent sessions complete different Ontology Work Units using only the run
  path and Work Unit ID as prompt-level handoff.
- A fresh Agent can understand and continue an unfinished unit from files without prior chat.
- Missing inputs and incomplete dependencies block explicitly.
- Source, coverage, competency-question, dependency, output-contract, and Ontology-scope references
  are complete and validated, including stale-input detection.
- One stable candidate, its review, Batch plan, and submitted content are bound by the same canonical
  content hash; changing semantic content invalidates the old review.
- A representative candidate larger than one live platform Batch, including hundreds of Entity
  items and Entity Relations, is deterministically split and completes ordered dry-run/apply.
- Merged outputs pass local structural checks, Ontology-level independent review, platform dry-run,
  apply, and competency-question/retrieval acceptance.
- The fast workflow can be rerun after changing one task or prompt without performing strict Harness
  activation, platform workflow-event publication, or retrospective generation.
- No backend, database, MCP, or frontend change is required for the first version.
