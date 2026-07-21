# R1.1-006 轻量共享建模目录与分片协作设计

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-006
- Downstream contract: `docs/requirements/requirements-v1.1.md` R1.1-007
- Status: realigned with R1.1-007; independent plan re-review PASS; implementation pending
- Priority: modeling quality and retrieval quality first

## Goal

Let multiple local Agent sessions share complete task information and work on bounded modeling
units without requiring the coordinating Agent to copy large context through prompts. Keep the
implementation small enough that a developer can inspect files, edit one unit, and rerun only the
affected work without weakening model review, platform dry-run/apply, or retrieval acceptance.

## Boundary with R1.1-007

R1.1-006 is the independently testable collaboration substrate for R1.1-007, not an execution
Profile of its own.

R1.1-006 owns:

1. the repo-local Shared Modeling Directory and its current-state file contracts;
2. bounded Work Unit assignment, stable input references, and stale-input detection;
3. deterministic validation, Ontology-level merge, candidate hashing, and Batch planning;
4. integration evidence that reviewed candidates can complete real platform dry-run/apply and
   competency-question/retrieval verification.

R1.1-007 owns Profile selection, the shared modeling method, continuous user conversation,
subagent clarification and business-change coordination, capability Skills and Agent wiring,
Harness activation/failure policy, credential loading, and automatic Build Session, Lease,
workspace-version, idempotency, and submission handling. R1.1-006 exposes data and deterministic
operations that those adapters consume; it does not duplicate them.

R1.1-006 remains independently acceptable before R1.1-007 is implemented. Its end-to-end
acceptance may drive the existing authenticated platform interface with a thin test driver or
explicit coordinator calls. That proof does not turn the driver into the ordinary Local Modeling
Mode entry point and does not pre-implement R1.1-007 automation.

## Current minimal scope

All participants run on one development machine against the same repository checkout. A gitignored
directory under `workspaces/modeling-runs/<run-id>/` stores current collaboration state. The
platform continues to own applied semantic state, Modeling Batch dry-run/apply, and retrieval
results, but it does not store every intermediate collaboration step through this directory.

The initial implementation needs only:

1. small repo-local commands/modules to initialize, inspect, and validate the directory;
2. human-readable Markdown for the business brief and JSON for indexes, tasks, status, results,
   candidates, reviews, Batch plans, and verification;
3. one coordinator writer for shared/Ontology files and one assigned writer for each Work Unit;
4. atomic JSON replacement so another Agent never reads a partially written file;
5. deterministic operations to reset a specifically named Work Unit, merge one Ontology candidate,
   and plan platform-sized Batches.

No background service, database migration, API, event recorder, dynamic scheduler, Profile router,
Harness controller, credential manager, Agent definition, or generic file store is required.

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
      batch-plan.json    # logical partitions and materialized request hashes
      verification.json  # post-apply competency-question and retrieval results
```

`run.json` records stable local identifiers and the non-secret platform references needed for final
integration. A Build Session reference may be bound by the acceptance driver or a later R1.1-007
adapter, but no credential, Lease token, or API key is stored. `task.json` is self-contained except
for stable relative paths into `shared/`, the fixed source corpus, and completed dependency units.
A worker receives only the run directory and Work Unit ID as dynamic business handoff; stable role
methods or Skills are outside this requirement.

The directory is not a clarification mailbox. A worker that needs business clarification stops and
returns the question to the coordinating Agent through the active Runtime. R1.1-007 defines how the
coordinator answers or consults the user.

### Minimum data contract

This is a small closed contract for the experiment, not a generic metadata framework. The first
implementation validates at least these fields and rejects unknown references:

| File | Required content |
| --- | --- |
| `run.json` | `schema_version`, `run_id`, non-secret Project/Build Session references, paths for brief/source index/coverage, indexed Work Units (`work_unit_id`, `ontology_id`, task/status/result paths), and indexed Ontology candidate/review/batch-plan/verification paths |
| `source-index.json` | `sources[]` with unique `source_id`, stable `locator`, declared scope, and current `content_hash` |
| `coverage.json` | `competency_questions[]` with ID/text/acceptance and `items[]` with unique `coverage_id`, `source_ids`, `competency_question_ids`, `ontology_id`, `work_unit_id`, and current status |
| `task.json` | `schema_version`, `work_unit_id`, `ontology_id`, `source_ids`, `coverage_ids`, `competency_question_ids`, `dependency_work_unit_ids`, stable input paths, `input_fingerprint`, and an `output_contract` naming the result schema and allowed command kinds |
| `status.json` | matching unit identity, `pending \| working \| ready \| blocked \| accepted`, optional bounded blocker codes/summary, and current update time |
| `result.json` | matching schema/unit/Ontology/input fingerprint and source/coverage/question IDs, `modeling_items`, explicit `gaps`, and a short summary |
| `candidate.json` | Ontology ID, contributing unit IDs, deterministic semantic items, and `candidate_hash` |
| `review.json` | `candidate_hash`, `PASS \| REVISE \| BLOCKED`, and bounded structured findings |
| `batch-plan.json` | `candidate_hash`, Ontology ID, ordered logical Batch membership/dependencies, stable `client_batch_id`, materialization state, platform `batch_id` after first submission, and exact immutable-content hash for each materialized Batch |
| `verification.json` | candidate/Batch references, executed competency questions/retrieval checks, results, explicit gaps, and verdict |

`modeling_items` use the existing platform `ModelingItemInput` shape: stable `client_item_id`,
`command_kind`, `payload`, `depends_on`, evidence references or inline evidence, rationale, and
competency-question IDs. Allowed command kinds come from an injected snapshot of the current
platform Modeling Context/compiler registry instead of a copied permanent list. The first quality
run must exercise at least `create_entity` and `create_relation`, as well as the schema commands
those instances require.

The validator resolves every source, coverage, competency-question, dependency, path, and output
contract reference and checks that it belongs to the declared Ontology/Work Unit scope. It verifies
the stored input fingerprint against referenced current inputs and blocks stale results from merge.
It never assumes that any input-byte change necessarily changes model semantics.

When used alone, R1.1-006 resolves a stale result conservatively by rerunning its Work Unit. When
used through R1.1-007, the affected subagent may instead return `no_change`, `modify_existing`, or
`remodel` directly to the coordinator. A `no_change` assessment may rebind the result to the new
input fingerprint only when the coordinator records a bounded reason and proves that normalized
semantic content is unchanged. If that cannot be proved, the unit is rerun. This resolution updates
current files; it does not create a mailbox or version history.

Hashes use one deterministic rule: SHA-256 over UTF-8 JSON serialized with sorted object keys,
compact separators, and list order preserved; raw Markdown/source files use their byte-level
SHA-256. An input fingerprint hashes a path-sorted list of relative path plus content hash.
Candidate items are topologically ordered with `client_item_id` as the tie-break before hashing.
The candidate hash covers normalized semantic items and stable contributor IDs, but excludes input
fingerprints, timestamps, review state, and transport-only fields. This lets an explicitly accepted
`no_change` input rebind preserve review/Batch reuse while any semantic edit changes the candidate
hash. The rule is implemented once and covered by repeatability tests.

`status.json` is mutable current state rather than an audit log. First-version transitions are
`pending -> working -> ready | blocked -> accepted`. The coordinator may reset a named failed or
stale unit after inspecting its files. There is no automatic lease, TTL, epoch, event replay, or
automatic remodeling transition.

## Roles and writes

- The coordinating Agent creates the run, owns `run.json` and `shared/`, assigns Work Units, merges
  results, requests platform integration through the active adapter/driver, and evaluates retrieval
  acceptance.
- A modeling Agent reads shared files and its dependencies, then writes only its assigned unit's
  `status.json` and `result.json`.
- A reviewer reads the same shared state plus `candidate.json` and writes the Ontology
  `review.json`; it does not choose a Profile or Harness policy.
- Human debugging may directly correct brief, coverage, or one task file and rerun the affected
  unit. The initializer/validator reports malformed, missing, or stale files clearly.

Different Ontologies may be modeled in parallel. Same-Ontology parallelism is disabled by default;
the coordinator may enable it only for explicitly disjoint coverage scopes and must merge before
dry-run.

### Stable Ontology candidate and platform Batches

The coordinator merges accepted unit results into one `candidate.json` per Ontology. Its
`candidate_hash` covers the canonical semantic content and stable contributor IDs, excluding the
hash field and local execution metadata.

`review.json` records the candidate hash, verdict, and findings. `batch-plan.json` records the same
hash and deterministic logical Batch membership. Any semantic change to `candidate.json`
invalidates both files and requires regeneration plus a new review. A non-semantic input rebind that
preserves the candidate hash may reuse them. Current files may be atomically replaced; no immutable
history is required.

The planner consumes all active Modeling Batch capacity limits supplied by the current platform
integration: `modeling_batch_max_items`, `modeling_batch_max_request_bytes`,
`modeling_batch_max_inline_evidence`, and `modeling_batch_max_evidence_excerpt_chars`. It
topologically orders items and deterministically partitions them without owning authentication or
submission. Item count, serialized request bytes, and total inline-Evidence count can cause a
deterministic split. One inline excerpt above the per-excerpt limit cannot be fixed by splitting;
the plan blocks before submission until the coordinator replaces it with a valid exact excerpt or
an existing platform Evidence Reference without weakening source fidelity.

Platform `depends_on` and item-output references are Batch-local. R1.1-006 must not submit a
cross-Batch `client_item_id` reference. The logical plan may retain a cross-Batch dependency, but
the integration driver/adapter performs Batches in dependency order. After a predecessor Batch is
successfully applied, it captures returned stable resource IDs/IRIs and refreshes Modeling Context;
the next Batch is then materialized with concrete references. Only same-Batch references remain in
the submitted `depends_on` list.

Each materialized Batch receives one stable `client_batch_id` before its first submission and
records an immutable-content hash over the same normalized content the platform treats as the
Batch identity: `{ontology_id, items}` with Items sorted by `client_item_id` and set-like Item
reference lists normalized deterministically. Mode, Lease token, current workspace version, and
idempotency key are Attempt fields and are excluded from that hash. The first dry-run response must
bind the plan entry to the returned platform `batch_id`; apply must reuse the same
`client_batch_id`, return the same `batch_id`, and preserve the immutable-content hash while using a
new Attempt/idempotency identity.

The real dry-run and apply envelopes are each serialized before submission because Attempt fields
have different byte sizes. If an unsubmitted materialized partition exceeds any splittable current
limit, it is deterministically split and `batch-plan.json` is replaced. An overlong single excerpt
or single Item that cannot fit blocks explicitly. Already submitted immutable Batches and their
stable `client_batch_id` are never mutated or repartitioned.

## Quality-preserving workflow

1. Freeze or identify the source corpus used by the run.
2. Write one concise business brief, competency questions, source index, and coverage map.
3. Split work by Ontology and bounded coverage scope.
4. Launch fresh workers with directory path plus Work Unit ID only.
5. Validate result shape and references; merge one stable candidate per Ontology.
6. Run one independent semantic review bound to the candidate hash.
7. Deterministically split the reviewed candidate into ordered logical Batches within all supplied
   live capacity limits.
8. Through the existing acceptance driver or a later Profile adapter, materialize each Batch,
   verify its candidate/request hashes and actual request size, dry-run, apply, refresh Modeling
   Context, and return Findings only to affected units.
9. Execute recorded competency questions and semantic retrieval checks; update coverage based on
   actual results.

Standalone directory initialization, validation, merge, planning, and targeted reruns do not
require Harness activation or platform workflow-record publication. This component property does
not define Local Modeling Mode behavior: when R1.1-007 selects Local Modeling Mode, its default
Harness and failure contract apply; Formal Modeling Mode follows its own adapter contract.

## Failures

- Missing or invalid shared input: mark the unit `blocked`; do not infer the missing content.
- Stale input fingerprint: block merge until the unit is rerun or the R1.1-007 impact-assessment
  seam explicitly proves and records `no_change`; do not automatically force or skip remodeling.
- Business clarification needed: stop and return the question to the coordinating Agent through the
  Runtime; do not create a shared-directory mailbox.
- Incomplete dependency: keep the dependent unit `pending` or `blocked`.
- Malformed result: report the schema error and rerun only that unit.
- Cross-unit semantic conflict: resolve during Ontology merge before dry-run.
- Candidate/review/Batch hash mismatch, or dry-run/apply returning different `batch_id` for one
  planned `client_batch_id`: stop; do not treat the apply as the reviewed immutable Batch.
- Cross-Batch item reference in a materialized request: block before submission and resolve it from
  the applied predecessor's returned resource identity.
- Oversized materialized request or inline-Evidence count: split the unsubmitted logical Batch
  deterministically; an unresolved dependency, overlong excerpt, or unsplittable Item blocks before
  submission.
- Later Batch failure: retain the already applied valid prefix, record the current failed Batch,
  fix or regenerate from platform current state, and run final retrieval acceptance only after the
  complete plan succeeds. R1.1-006 does not promise cross-Batch atomic rollback.
- Platform Finding: map it back to affected units and rerun only those units.
- Worker loss: start a fresh Agent against the same unit files; no chat recovery is required.
- Authentication, Lease, or Harness failure: report through the active driver/Profile contract;
  R1.1-006 neither bypasses nor redefines that behavior.

## Future productization

The following are intentionally deferred: server-hosted collaboration storage, cross-machine
synchronization, immutable versions, event/audit history, participant authentication, role-scoped
credentials, dynamic claims, TTL/fencing, automatic crash recovery, distributed scheduling,
conflict-free merge, UI, retention policy, and formal export/import.

R1.1-007 may add local/formal adapters, automatic protected platform submission, Harness behavior,
and capability Skills without changing this directory's Work Unit, stable-reference, candidate, or
quality semantics. Those are downstream execution capabilities, not future R1.1-006
productization.

## Acceptance

- At least two independent Agent sessions complete different Ontology Work Units using only the run
  path and Work Unit ID as dynamic prompt-level handoff.
- A fresh Agent can understand and continue an unfinished unit from files without prior chat.
- Missing inputs and incomplete dependencies block explicitly; clarification is returned to the
  coordinator and is not persisted as a directory mailbox.
- Source, coverage, competency-question, dependency, output-contract, and Ontology-scope references
  are complete and validated, including stale-input detection.
- Stale input cannot enter merge without rerun or explicit semantic `no_change` resolution; a
  non-semantic rebind preserves the candidate hash, while semantic content changes invalidate the
  old review and Batch plan.
- One stable candidate, its review, Batch plan, and submitted content remain linked by candidate and
  materialized immutable-content hashes. Each planned Batch fixes `ontology_id` and
  `client_batch_id`; dry-run/apply return the same platform `batch_id` for that identity.
- A representative candidate larger than one live platform Batch, including hundreds of Entity
  items and Entity Relations, is deterministically split and completes ordered dry-run/apply.
  Submitted payloads contain no cross-Batch `depends_on` or item-output reference; later payloads use
  concrete predecessor resource IDs/IRIs.
- Every submitted Batch satisfies current item, serialized-byte, inline-Evidence-count, and
  per-excerpt-length limits; unsplittable violations block before platform submission.
- Merged outputs pass local structural checks, Ontology-level independent review, platform dry-run,
  apply, and competency-question/retrieval acceptance.
- Directory primitives and targeted reruns can be tested independently of Harness/Profile routing;
  R1.1-007 remains responsible for ordinary Local/Formal execution behavior.
- No backend, database, MCP, frontend, Profile, Harness, credential-management, or Agent-Skill
  change is required for the first R1.1-006 implementation.
