# Semantic handoff and returned execution results

Use this reference to decide what Modeling supplies and what execution results it needs back. The selected
Task controls stages, schemas and approvals. This table does not assign platform operations to
Modeling or introduce a universal execution sequence.

| Work | Modeling supplies or decides | Protocol execution result to inspect |
| --- | --- | --- |
| Scope | Business-supported meaning, proposed scope, gaps and questions | Actual authorized Project/Ontology bindings when needed |
| Candidate | Complete neutral semantic content and dependencies | Translation receipt or a concrete conflict |
| Application | Approved semantic revision and answers to semantic conflicts | Applied Batch/Attempt bindings and version confirmation; business reads are separate |
| Retrieval | Public consumer questions and required semantic relationships | Scoped facts, relations, pagination and explicit completeness |
| Handoff | Own artifacts, outstanding unknowns and semantic findings | Bound execution results required by the Task |

For a Task mounting R4.0-024, perform the production association self-check before whole-run
terminal and handoff. Protocol supplies actual governed scan candidates and read completeness;
Modeling distinguishes grounded defects, justified independent resources, business unknowns and
unread scope. Correct confirmed defects through the same reviewed revision/application flow and
inspect affected rechecks before completion. Degree zero is a candidate, not an automatic defect;
RDF incoming/outgoing links, predicate usage and formal structural references all matter. The
Coordinator records scope, dispositions and remaining work through the existing sidecar/messages.
The self-check does not grant independent acceptance PASS or reinstate tracing-package duties.

Build Session creation, leases, Batch envelopes, request schemas, idempotency and platform calls
belong to Protocol. Do not reconstruct these from a high-level recipe or change business meaning
in response to a purely mechanical translation failure.

## Explicit unknowns

Represent an unresolved business decision through the mounted semantic contract. Where the contract
uses a model-local `kind=explicit_unknown` resource, preserve its stable identity, affected semantic
scope, unanswered business question, source basis and rationale, with no asserted answer value.
Connect it to the affected model meaning so a governed consumer can observe the uncertainty.
Narrow the unknown to the specific unconfirmed business meaning, and retain other source-confirmed
facts and the current scope. Physical source structure and samples do not establish customer
business rules, business-wide legal value universes or permissions. A declared source enum/CHECK
can describe that source column's allowed values; sample values alone cannot.
Keep confirmation state separate from delivery state; every
`deferred`, `unknown` or `out-of-scope` disposition carries its reason, impact and next responsible
role/input in the existing reason/note or handoff content; do not add a field or enum for it. Do not
create source-row instances or a platform-domain feature to carry the unknown.

## Retrieval completeness

Check that returned results refer to the expected candidate/revision and authorized scope. Preserve
asserted versus inferred status, warnings, pagination and explicit completeness. A truncated page,
missing scope or inaccessible relation is not proof that the complete model supports the answer.

The platform returns facts, topology and state. The consumer interprets business
answers; Modeling must not claim an independent acceptance result from its own successful query.

## Respond to findings

- Source contradiction or unresolved business meaning: ask the grounded question through the
  declared channel, or preserve an explicit unknown.
- Semantic candidate or deterministic write finding: correct only the observed semantic defect and hand off
  the required complete revision.
- Request-shape, lease, identity-binding or execution failure: return the exact conflict to
  Protocol; do not invent platform mechanics or change the candidate to bypass it.
- Incomplete retrieval: identify the missing scope/path/page or semantic row and request the needed result.
  Do not infer an answer from missing or inaccessible facts.

Authorization, attempt accounting and run lifecycle belong to the Delivery host. Do not start a
replacement modeling session or an acceptance consumer from this role.

## R4.3 complete business chain and early public feedback

Before each stage execution and at final handoff, reconcile current candidate item identities with
Protocol's approved plan coverage: definitions, relations, shared identities, cross-Ontology targets
and necessary dependencies must have actual planned/applied correspondence, or explicit supported
unknown/out-of-scope/deferred dispositions, each with a concrete reason, impact and next responsible
role/input. Use `protocol_check_plan_coverage` as a deterministic diagnostic, then review business
meaning yourselves; candidate existence, definition counts and mechanical COMPLETE do not prove
semantic completeness. Coordinator's first stage dispatch names the current chain, necessary shared
dependencies and the global scope/remaining-stage overview; later detailed candidates are not a
prerequisite and topology or slice count is not preselected. Coordinator approves the full
current-stage scope and dependency-ordered
plan list once. Protocol calls `protocol_execute_approved_plans` by immutable reference continuously;
unchanged approved plans remain reusable, and a valid current-version dry-run is retained through its
immediate apply without a repeated per-batch semantic review. Revalidate only when the plan/content,
binding, approval or workspace version makes the proof stale.
Correct changed content or real errors through the current revision/review/reconciliation channels.

A complete small chain, usually an existing business slice, can execute before all later scenarios
have detailed candidates/plans. Include its necessary shared dependencies and reuse their actual
identities later; retain the full authorized scope and remaining work. After its confirmed successful
application, reuse the existing R4.0-015 bounded public feedback path with a few high-value public
questions. Keep model expression, retrieval acquisition and Consumer understanding separate in
failure evidence and repair only the evidenced layer. Final independent acceptance cannot repair
production; hidden questions/answers never enter production. Public success is interim feedback.
Mapping/metric business unknowns remain explicit; source schema is not business truth. Confirmation and
delivery state stay separate; a legitimate deferred disposition is not whole-scope completion, and an
analyzed-but-undelivered item is not a generic unknown. Do not materialize mapping semantics without
the applicable mapping approval.

For that early feedback, Coordinator requests Delivery's existing `public-feedback` evaluation
with a verified published `materialization_progress` checkpoint, current freeze_id and the small
selected approved public question_ids. Reuse enabled checkpoint/CQ selectors; do not change the
running Task or require final production_handoff first. If this checkpoint path is unavailable,
report feedback not executed and the exact missing prerequisite. Delivery obtains actual governed
responses and Consumer answers; production consumes only authorized public feedback and preserves
original receipts. This checkpoint prerequisite is the existing R4.0-015 path, not a new phase gate.

R4.3-015: trust the tool's bound applied Attempt and version confirmation; do not routinely read
all resources or compare every approved statement after successful apply. Applied and business
quality feedback are separate: not_evaluated is not semantic PASS. A stage with complete approved
coverage and available dependencies may advance without a mandatory question round; choose later
public questions by business value, not once per batch/stage. Keep dry-run validated separate from
applied. Pending/applying/recovering, lost replies or unconfirmed identity use the original request
and Attempt recovery; never change keys to replay possible writes. Actual business reads revealing
missing/wrong writes are platform defects, not a reason to add a permanent full-audit routine.

For the bounded feedback reading window, Delivery sends sourced delivery_guidance to Coordinator;
Coordinator sends Protocol an existing reply-required Team message to pause new dry-run/apply
submissions. Let in-flight continuous calls return and report actual receipts/pending writes before
feedback starts. Analysis, candidate preparation and later planning may continue. The window lasts
through Consumer reads and the final binding check. Release this normal submission wait only when
the original evaluation operation actually ends, including partial/unavailable/superseded results;
a timeout/lost reply requires querying that same operation, not launching another or releasing early.
Unknown writes and explicit user pauses remain constrained. Do not require a retained owner to exit.

Quality defects pause only affected content and its real dependents, including shared references;
independent work continues. Revise/review/dry-run/apply only changed content, then recheck affected
public questions and associations. Preserve unresolved defects as REVISE and incomplete reads or
undetermined causes as PARTIAL. At whole-run completion retain actual governed association checks,
shared identity/global coverage reconciliation and the complete independent Consumer/Judge verdict;
local public feedback and successful application never replace that final read-only acceptance.
