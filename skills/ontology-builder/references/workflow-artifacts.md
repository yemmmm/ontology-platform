# Workflow Artifacts and Events

Use these structures as the single handoff format. The platform validates shape, ownership,
secrets, size, versions, idempotency, and sequence; the Agent remains responsible for truth and
business quality.

## Business Knowledge Pack

Persist JSON with:

- `business_goal`, `success_conditions`, `scope`, `non_goals`;
- `sources`: stable source ID, requested/final location, title, authority, freshness, scan status;
- `knowledge_items`: stable ID, terms/aliases, actors, objects, events/records, definitions;
- `processes`, `state_changes`, `rules`, `constraints`, `exceptions` and effective scope;
- `identity_lifecycle_boundaries`: identity, lifecycle, time, region, and version boundaries;
- `operations`: purpose, input, output, side effects, idempotency, and constraints;
- `competency_questions`: stable ID, priority, and concrete success condition;
- `evidence_index`: source item to exact Evidence Reference IDs;
- `ambiguities`, `source_conflicts`, `knowledge_gaps`, `questions`, and `deferred_items`.

Do not include Class, Property, RelationType, graph, or Modeling Batch decisions.

## Modeling Coverage Matrix

Persist JSON rows with:

```json
{
  "coverage_item_id": "stable-id",
  "source_ids": ["source-id"],
  "knowledge_item_ids": ["knowledge-id"],
  "competency_question_ids": ["cq-id"],
  "model_element_ids": [],
  "evidence_reference_ids": ["reference-id"],
  "status": "AMBIGUOUS",
  "reason": "Identity boundary needs confirmation",
  "last_reviewed_artifact_version": 1
}
```

Allowed status is `MODELED`, `DEFERRED`, `AMBIGUOUS`, `UNSUPPORTED`, or `MISSING`. Check source,
business, competency-question, evidence, and lifecycle coverage separately.

## Modeling draft

Persist JSON containing the selected competency questions, vertical-slice rationale, proposed
concept/identity/lifecycle/relation/fact/rule/Operation elements, Evidence Reference mapping,
Coverage Matrix updates, Modeling Batch draft, assumptions, and explicit excluded items.

## Review report

Persist JSON with `verdict: PASS | REVISE | BLOCKED`, reviewed version IDs, source coverage checked,
dry-run Attempt ID and Finding fingerprints, structured quality issues, required rework, accepted
limitations, and rationale. A reviewer never edits the draft.

## Verification report

Persist JSON with each target competency question, query used, persisted result summary,
validation result ID/status, lineage target/status, Evidence References, limitations, and
`PASS | FAIL`. Do not copy platform facts when a stable related-resource ID is available.

## Artifact rules

Create with `mcp:create_modeling_workflow_artifact`. Use one stable `artifact_key` per logical
product, a new `client_version_id` per immutable version, and exact
`supersedes_workflow_artifact_id` for every version after v1. Read with
`mcp:list_modeling_workflow_artifacts` or `mcp:get_modeling_workflow_artifact`.

## Execution Event

Append with `mcp:record_modeling_execution_event`. Always set stable `client_event_id`, workflow
name/version, phase, event type, status, report source, actor role, prompt version when available,
summary, exact input/output Artifact version IDs, stable related-resource IDs, unresolved items,
blockers, and next step. Record Runtime/model/effort, duration, tokens, or cost only when observed;
use absent/unknown rather than zero.

External Agents may report only `agent_reported` or `user_reported`; never claim
`platform_observed`. Read with `mcp:list_modeling_execution_events` and
`mcp:get_modeling_execution_event`.

## Question state

- First ask: `question_asked + open`, no expected head.
- Initial answer: `answer_recorded + answered|skipped|uncertain`, expected head equals current
  open/reopened event.
- Reopen: `question_asked + reopened`, expected head equals current resolved event.
- Correct an answer: expected head and `supersedes_execution_event_id` both equal the current
  resolved event.

An answered response needs user-visible answer text or an Interview Answer ID. Skipped/uncertain
needs an explicit reason. A `question_state_conflict` means reload the current head; never branch.

## Structured quality issue

Reviewer `quality_issues` must be directly accepted by
`app.api.schemas.ModelingQualityIssue`. Extra fields are forbidden.

Required fields:

- `issue_category`: `knowledge_omission`, `term_conflict`, `identity_error`, `relation_error`,
  `granularity_error`, `insufficient_evidence`, `competency_question_gap`, `over_modeling`,
  `stale_knowledge`, or `other`;
- `introduced_phase`: `recovery`, `global_scan`, `business_confirmation`, `core_modeling`,
  `dry_run`, `review`, `apply`, `verification`, `expansion_or_handoff`, or `unknown`;
- `detected_phase`: one workflow phase above, but not `unknown`;
- `detected_by_role`: `business_organizer`, `modeler`, `reviewer`, `main_agent`, `user`, or
  `platform`; an independent reviewer still uses `reviewer`;
- `severity`: `critical`, `high`, `medium`, or `low`;
- `preventable_at`: one workflow phase above or `unknown`;
- `description`: non-empty, at most 10,000 characters.

Optional fields:

- `rework_count` and `rework_duration_ms`: non-negative integer or null;
- `root_cause`: `unknown` by default or `hypothesis`;
- `root_cause_hypothesis`: at most 4,000 characters; required only when `root_cause` is
  `hypothesis` and forbidden when it is `unknown`.

Record-ready example:

```json
{
  "issue_category": "knowledge_omission",
  "introduced_phase": "global_scan",
  "detected_phase": "review",
  "detected_by_role": "reviewer",
  "severity": "high",
  "rework_count": 1,
  "rework_duration_ms": 120000,
  "preventable_at": "global_scan",
  "root_cause": "hypothesis",
  "root_cause_hypothesis": "The organizer omitted a lifecycle exception.",
  "description": "The draft treats cancelled work as executable although the source forbids it."
}
```

Before returning, run every issue through
`ModelingQualityIssue.model_validate(issue).model_dump(mode="json")` using the repository model.
Return those objects unchanged in the review report and Event. If validation fails, the reviewer
fixes its output; the main Agent never performs an undocumented rewrite. Do not present a root-cause
hypothesis as platform fact.
