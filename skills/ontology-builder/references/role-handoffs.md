# Role Handoffs

Start each subrole in a fresh context. The main Agent supplies versioned inputs and receives
record-ready outputs. Subroles have no platform credential, write MCP, lease, or hidden context.

## Business organizer

Inputs:

- user goal and confirmed constraints;
- source inventory plus accessible sources/key excerpts;
- current Project/Session summary and existing Pack/Matrix versions;
- current question heads and competency questions.

Outputs:

- Business Knowledge Pack JSON;
- Modeling Coverage Matrix JSON;
- at most three blocking questions;
- scanned/deferred/missing source list and concise handoff summary.

Forbidden: ontology schema, Class/Property/RelationType, graph identifiers, batch items, lease,
apply, or claims of completeness.

## Modeler

Inputs:

- exact confirmed Pack and Matrix version IDs/content;
- target competency questions and success conditions;
- exact Evidence References and current Modeling Context/read model;
- accepted ambiguity/deferred decisions.

Outputs:

- smallest useful vertical-slice rationale;
- Markdown modeling draft and immutable dry-run Modeling Batch draft with stable client item IDs;
- Coverage Matrix changes and evidence mappings;
- assumptions, unsupported items, and handoff summary.

For a Codex modeler, use `references/modeler-handoff.schema.json` as the unchanged
`--output-schema` file. Return its seven required top-level fields directly. The schema correlates
each item `command_kind` with the allowed `create_class`, `create_property`,
`create_relation_type`, or `create_operation` payload and intentionally excludes lease, actor,
graph override, credential instance, and secret-bearing fields. Do not create an ad-hoc schema.

Forbidden: rereading unrelated source scope without a gap request, changing confirmed business
meaning, acquiring/renewing a lease, applying, or declaring review PASS.

## Independent reviewer

Inputs:

- original source inventory and key excerpts/access to sources;
- Pack, Matrix, modeling draft, and Modeling Batch version IDs/content;
- current Modeling Context and every dry-run Finding with stable fingerprint;
- competency questions and accepted limitations.

Outputs:

- `PASS`, `REVISE`, or `BLOCKED`;
- source/business/question/evidence/lifecycle coverage disposition;
- `quality_issues` that pass `ModelingQualityIssue.model_validate` exactly, plus exact
  Finding/resource references;
- required rework, blockers, residual risk, and concise rationale.

Before returning, validate each issue with the repository's real Pydantic
`app.api.schemas.ModelingQualityIssue`, then return its `model_dump(mode="json")` result unchanged.
Fix invalid output inside the reviewer context. Do not ask the main Agent to rename categories,
roles, severities, or extra fields.

Forbidden: editing Artifacts, changing the batch, obtaining credentials, applying, weakening a
gate, or reviewing only the organizer's summary without original-source evidence.

## Main Agent

The main Agent alone asks the user, persists Artifacts/Events, creates Evidence References, calls
dry-run, owns credentials, obtains/releases the lease, applies the exact reviewed batch, runs
verification, checkpoints, and completes/cancels the Session. It evaluates subrole output instead
of blindly accepting it.

## Runtime fallback

When independent contexts are unavailable, record a decision/event declaring
`single_agent_fallback`, run stages serially, and treat the review as self-review rather than
independent evidence. Preserve the same Artifact/Event contracts and gates.
