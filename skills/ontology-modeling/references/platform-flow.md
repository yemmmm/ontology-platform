# Platform flow and evidence

Use the concrete registered tool schemas or public API contract exposed to the current modeling
Agent. Do not invent an operation, payload, alternate storage, or orchestration layer.

## Sequence

| Phase | Modeling Agent owns | Required evidence |
|---|---|---|
| Scope | interpretation, gaps, questions | declared source list and consumer questions |
| Session | Build Session creation and lease | Project, Ontology, Build Session IDs |
| Schema | vocabulary, relations, Shapes, rationale | dry-run findings and applied immutable Batch ID |
| Negative proof | intentionally invalid instance | rejected Batch ID and Shape violation |
| Instances | valid facts and provenance | dry-run findings and applied immutable Batch ID |
| Validation | response to deterministic findings | validation ID, `conforms`, findings |
| Reasoning | interpretation of consistency evidence | reasoning ID, `consistent`, findings |
| Retrieval | scoped query and completeness checks | request, public results, truncation/completeness |
| Closure | checkpoint and completion request | revision/checkpoint and completed state |
| Consumption | read-only interpretation | blind answer with evidence and unknowns |

Apply schema before instances. A rejected negative Batch must remain unapplied. Never repair a failed
payload in the Host relay; return the failure to the modeling Agent.

## Exact-request fallback

Use the fallback only after confirming that the modeling Agent's connected interface cannot perform
the needed mutation and after adding the current public OpenAPI fragments or equivalent
allowed-operation request schemas to its declared visible inputs. Preserve:

- the exact Agent-selected method, path, and body;
- a canonical request hash before transport;
- the exact response status and body;
- `host_initiated_retries=0`;
- proof that only authentication and base URL were added.

If the Host changes semantic content, the attempt is invalid.

## Explicit unknown representation

Define a model-local resource shape for unresolved business decisions. Each instance must be
queryable and include:

- `kind=explicit_unknown`;
- a stable identifier;
- the affected subject or semantic scope;
- the unanswered plain-business question;
- source evidence and rationale;
- no asserted answer value.

Connect the resource to the affected model element, validate it with a Shape, and include it in the
governed query projection. This is ontology data, not a new platform domain concept.

## Attempt ledger

For an evaluation with a fixed attempt budget, the Host writes append-only JSONL outside the frozen
Agent input. Write `modeling_started` before each launch and exactly one terminal
`modeling_completed` or `modeling_blocked` event afterward. Each event includes attempt number,
timestamp, fresh Project/Ontology/Build Session identifiers when available, subagent identifier, and
evidence locator. Exclude credentials, hidden answers, prompts, and model content.

## Retrieval checks

Query an authorized ontology scope. Request the resource kinds, related expressions, fact/relation
expansion, provenance, and fields needed by the consumer questions. Check pagination, truncation,
warnings, and explicit completeness before judging semantic quality.

The platform returns facts, topology, provenance, state, and warnings. The consumer interprets them;
the platform must not manufacture a domain-specific answer.

## Failure handling

- Source contradiction: ask one business question.
- Unavailable answer: model a scoped `explicit_unknown`.
- Batch finding: correct only the evidenced defect and dry-run again.
- Validation or reasoning finding: keep the session open and report the exact finding.
- Incomplete query: correct query scope/projection/pagination; do not guess the missing answer.
- Attempt limit reached: stop, preserve evidence, and report.
