# R2.3-005 Modeling Team Runner Acceptance Design

## Status and sources

- Status: Design approved by plan review; implementation pending
- Requirement: `docs/requirements/requirements-v2.3.md`, R2.3-005
- Base: R2.3-001 Team Runner/Codex adapter and R2.3-002 fresh-scope modeling workflow
- Delivery record:
  `docs/delivery/records/2026-08-03-r2-3-005-producer-runner-formalization-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-08-03-r2-3-005-modeling-team-runner-acceptance-test-plan.md`

## Goal

Formalize one Runner-managed Modeling Team task with exactly four persistent roles:
Coordinator, Modeling, Protocol, and Acceptance. Acceptance is a normal Team member and the
single owner of semantic acceptance, while Runner owns the bounded creation and recycling of two
temporary Examiner Agents for each acceptance round. The design proves the lifecycle and evidence
contract on one fresh, simple R2.3-002 source slice; it does not turn the Runner into a generic
multi-agent platform.

## Current minimal scope

The implementation should extend only the repository-local `modeling_team/` contracts, Runner,
Codex adapter, transport, evidence writer, and tests needed for the following:

1. A formal Profile loads exactly one Coordinator, Modeling, Protocol, and Acceptance Package.
   Three-role Profiles and the source-specialist role are not complete modeling workflows and must
   be upgraded or rejected. Historical files and retained evidence remain archival facts.
2. Runner starts the four persistent roles once. Acceptance keeps conversation context across
   rounds within that task and terminates with the other roles at task settlement. A new task gets
   a new Acceptance session; old dialogue, verdicts, and hidden context are never inherited.
3. Coordinator uses non-terminal Team Transport messages to assign a slice, receive independent
   Modeling-ready and Protocol-silent acknowledgements, and start an acceptance round. These
   messages are coordination state, not `report_task_result`, and do not settle an Agent. The
   authoritative acceptance ticket, child reports, and verdict use a separate Runner-owned local
   carrier; Team Transport never carries child terminal state.
4. Runner exposes one narrow, opaque, Acceptance-scoped child handle API. For each round it can
   start exactly one fresh Source Examiner and one fresh Platform Examiner, both from predeclared
   Packages. Children cannot spawn or communicate with other Agents, receive no expected answer or
   prior verdict, and cannot write the platform.
5. Runner accepts one automatic infrastructure retry per child with identical frozen input and a
   fresh session. A second infrastructure failure blocks the current round. Semantic disagreement
   is never retried as infrastructure.
6. Acceptance receives only the frozen ticket and two terminal reports, checks report sufficiency,
   compares source-grounded and platform-grounded evidence, records `PASS`, `FAIL`, or `BLOCKED`,
   and asks Runner to recycle only the two children. Acceptance remains alive.
7. Every verdict binds the question, slice revision, full model-state identity, ticket digest, and
   both report digests. A later platform write or model/slice revision invalidates an earlier PASS.
8. The real run is one fresh simple Dify Workflow-as-Tool `C -> B -> A` slice, followed by two
   sequential independent CQs on the same persistent Acceptance and fresh child pairs. Deterministic
   tests cover the failure branches; the real run does not intentionally manufacture FAIL/BLOCKED.

## Future productization (not a completion gate)

Runner-enforced write leases, a mechanical phase gate that rejects late platform writes, pause/resume,
automatic retry scheduling, persistent Acceptance across tasks, generalized child pools, a numeric
acceptance-round cap, and advanced Platform Examiner retrieval tuning are deferred. The current
design records late-write risk and relies on explicit Agent silence/cooperation; it must not claim
that cooperation is a mechanical write freeze.

## Architecture and ownership

| Component | Owns | Must not own |
| --- | --- | --- |
| Runner | fixed roster startup, child handles, session/process lifecycle, opaque capability checks, evidence ordering, cleanup | semantic answers, expected answers, verdict meaning, business ontology construction |
| Coordinator | serial phase orchestration, ticket freezing, retry/wait/revision decision, routing verdicts to Modeling/Protocol | changing the requirement-owned standard, reading raw source/platform evidence, creating children directly |
| Modeling | ontology structure/content and semantic repair after modeling-quality `FAIL` | platform calls, acceptance verdicts |
| Protocol | platform writes during modeling and platform receipts | semantic acceptance, child creation |
| Acceptance | multi-round evidence sufficiency check, comparison, verdict, reason classification; calls the scoped Runner capability | raw source access, platform query tools, platform writes, child process cleanup |
| Source Examiner | answerability and source-grounded conclusion from approved material | platform access, expected answer, prior dialogue |
| Platform Examiner | read-only platform retrieval and evidence-grounded conclusion | approved source access, writes, expected answer, prior dialogue |

Runner remains the only external entrypoint. Acceptance is started by Runner as part of the
four-role roster; it does not become a second launcher and does not call Codex's generic
`spawn_agent` capability. Acceptance keeps its ordinary Team Transport membership for the
Coordinator-facing task flow, but the scoped Runner capability below is the only path for child
lifecycle, child reports, and the authoritative verdict.

## Profile, Package, and child contracts

### Persistent roster

The formal Profile must contain exactly these stable roles and IDs (the IDs are configuration-owned,
not inferred from display names):

```text
coordinator -> coordinator Package
modeling    -> modeling Package
protocol    -> protocol Package
acceptance  -> acceptance Package
```

The Profile communication graph permits Coordinator to address all three working roles, Modeling and
Protocol to exchange modeling handoffs, and Acceptance to report only to Coordinator. Coordinator's
Package declares the Runner-owned `coordinator_publish_acceptance_ticket` and
`coordinator_get_verdict` capabilities; Acceptance's Package declares the Runner-owned
`acceptance_capability` for ticket get/ack, child lifecycle, and
verdict submission. Both capabilities have no arbitrary filesystem, process, or package access.
Acceptance's Package has Team Transport permission but no platform permission and no raw source
permission; Coordinator's capability does not grant it platform access.

### Child Package descriptors

Source Examiner and Platform Examiner are Runner-owned descriptors, not Profile members. They are
versioned with the Acceptance contract and selected only by a fixed kind enum:

```json
{
  "kind": "source_examiner | platform_examiner",
  "package_digest": "sha256",
  "platform_mode": "none | read",
  "can_team_transport": false,
  "can_spawn": false,
  "can_write": false,
  "max_children": 0
}
```

The Platform Examiner descriptor includes the basic, version-frozen read-only retrieval Skill:
approved interface selection, pagination/completeness checks, Evidence/lineage/query basis, and
the distinction between absent modeling and retrieval miss. No advanced recall tuning is required
in this increment.

### Runner acceptance capability and child API

The concrete Python names may follow repository conventions, but the two model-visible capability
surfaces and the child-local report sink have this fixed contract. Runner generates separate opaque
tokens and mounts a Coordinator-only endpoint in the Coordinator private config for ticket publish,
and an Acceptance-only endpoint in the Acceptance private config for ticket read, child lifecycle,
and verdict submit. Neither endpoint is Team Transport and neither is mounted into any Examiner:

```text
coordinator_publish_acceptance_ticket(coordinator_id, ticket_json, ticket_digest,
                                      requirement_ref, owner_revision)
    -> TicketReceipt                 # Coordinator-only Runner capability
coordinator_get_verdict(coordinator_id, acceptance_round_id, verdict_digest | null)
    -> ImmutableVerdictReceipt
acceptance_get_ticket(acceptance_id, round_id)
    -> ImmutableTicket
acceptance_child_start(acceptance_id, round_id, kind, input_ref, input_digest, ticket_digest,
                       request_id, attempt)
    -> opaque ChildHandle
acceptance_child_get_report(acceptance_id, round_id, child_handle, request_id)
    -> ImmutableExaminerReport
acceptance_child_recycle(acceptance_id, round_id, child_handle,
                         completion_ref, request_id)
    -> CleanupReceipt
acceptance_get_failure_record(acceptance_id, round_id, failure_digest)
    -> ImmutableInfrastructureFailure
submit_acceptance_result(acceptance_id, round_id, verdict_json, verdict_digest, request_id)
    -> VerdictReceipt
acceptance_get_verdict(acceptance_id, round_id, verdict_digest)
    -> ImmutableVerdictReceipt
```

Runner creates a task-scoped, local-only acceptance root with exclusive-create canonical JSON files.
The Runner stages a projected input for each child and returns only its opaque reference and digest.
The Source projection contains the question and approved source bundle; the Platform projection
contains the question, model-state/read scope, and read-only tool allowlist, never the source bundle.
The child receives a private, write-only report sink whose endpoint is not Team Transport. Runner
validates the report envelope and makes it available only through `acceptance_child_get_report`.
`coordinator_publish_acceptance_ticket` is the only ticket publish bridge: Coordinator freezes the
requirement-owned fields and calls this Coordinator-only Runner capability with the requirement
reference and owner revision. Runner validates the canonical artifact, source digests, question/source
binding, standard reference, and owner revision before exclusive-create publication. Acceptance can
only call `acceptance_get_ticket` and acknowledge/read that immutable artifact; it cannot define or
replace the question, approved sources, unknown policy, standard, or platform scope.
`submit_acceptance_result` writes the authoritative result once and emits a sanitized Coordinator
notification; it never uses terminal `TaskResult`. If that notification is lost, Coordinator uses
`coordinator_get_verdict` on its separate read-only Coordinator capability to recover the immutable
receipt. When `verdict_digest` is null, Runner returns the sole receipt for that acceptance round;
zero receipts returns not-found and multiple receipts fails closed. An exact duplicate Acceptance
submission also re-emits the notification.

The Coordinator publish endpoint validates only the live Coordinator runtime, its Coordinator token,
requirement reference, owner revision, canonical ticket digest, and single-publish round rule. The
Acceptance endpoint validates the live Acceptance runtime, its Acceptance token, active round, fixed
kind, input/ticket digest, `attempt ∈ {0,1}`, and one-child-per-kind cardinality. Each
child request has a caller-supplied stable `request_id` recorded in the local carrier; exact duplicate
requests replay the original receipt, while a different request ID with the same active child or
different digest fails closed. The Acceptance endpoint rejects arbitrary package paths, recipient IDs,
nested child requests, cross-round handles, and calls from Coordinator/Modeling/Protocol/Examiner.
A handle is bound to task ID, Acceptance runtime ID, round ID, child kind, input digest, ticket digest,
child session ID, and a request ID. The API never returns a process ID or credential to Acceptance.
Reports and verdicts are immutable exclusive-create artifacts; duplicate, overwrite, symlink,
path-escape, digest-drift, or replay attempts fail closed.

Verdict submission also uses a stable caller-supplied `request_id`. An exact retry with the same
request ID and verdict digest replays the durable `VerdictReceipt`; a different request ID or digest
for the same ticket/acceptance round fails closed. If the initial response is lost, Acceptance uses
`acceptance_get_verdict` to retrieve the immutable receipt before deciding whether to continue or
settle.

Start and recycle are idempotent only for the exact same request ID. A duplicate start with a
different digest or a second active child fails closed. `completion_ref` must be exactly one of
`terminal_report_digest` or `infrastructure_failure_digest`. The latter points to a Runner-written,
immutable record containing task/round/handle/input digests, child attempt, failure category,
failure reason, and timestamp; it is the only legal recycle evidence when no terminal report exists.
Runner allows attempt 0 plus one automatic attempt 1, then requires a round BLOCKED record. Recycle
stops the child, destroys its private session, temporary credentials, and private input tree, and
emits a cleanup receipt before the next round.

The immutable `CleanupReceipt` contains task ID, round ID, child handle digest, completion kind,
completion digest, cleanup status, destroyed-resource summary, and receipt digest. For an
infrastructure completion it also contains the matching `infrastructure_failure_digest` and typed
failure evidence references. Acceptance may retrieve the failure record only through
`acceptance_get_failure_record`; Runner validates the digest and binds it into the canonical
`BLOCKED/runtime-infrastructure` verdict. Acceptance never reconstructs failure evidence from a
free-form error string.

The Platform Examiner child receives a separate project-scoped read-only key created by the existing
host-owned key lifecycle. The local credential manifest binds key ID, Project, Ontology, ticket
digest, round, child input digest, creation receipt, and config digest. Its MCP config registers
only the ticket's minimal subset of these existing read tools: `check_platform_health`,
`get_project_build_context`, `get_build_session`, `get_modeling_context`,
`get_ontology_workspace_context`, `get_ontology_read_model`, `get_semantic_read_model`,
`query_semantic_context`, `semantic_sparql_query`, `describe_semantic_graph_set`,
`list_semantic_derived_pointers`, `inspect_semantic_projection_status`,
`list_evidence_references`, `get_evidence_reference`, `get_ontology_lineage`, and
`inspect_semantic_statement_provenance`, plus the four generic read wrappers
`list_semantic_validation_runs`, `get_semantic_validation_run`, `list_semantic_reasoning_runs`, and
`get_semantic_reasoning_run`. The four run wrappers must bind the ticket's Ontology/graph scope and
resolve Project ownership; they read Producer-created results and never start or rerun validation/
reasoning. Validation/reasoning mutation tools and all write/key/Project/Ontology tools are excluded.
The read key is revoked and plaintext destroyed on every child
terminal path, including timeout, crash, and BLOCKED; a post-revoke call must fail.

Every other Platform Examiner read call also passes through a child-local ticket-bound read shim.
The shim injects or verifies the exact Project, Ontology, graph-set, and source/ticket binding on
each request, rejects a different ontology/graph or an omitted binding before MCP dispatch, and
records request/response digests. The child is not given a raw unrestricted platform MCP socket.
This is a narrow scope-integrity wrapper for the current ticket, not a generalized security proxy or
multi-tenant authorization product.

## Frozen ticket and evidence inputs

The Coordinator creates a new immutable ticket revision for every round. Its canonical fields are:

```json
{
  "schema_version": "r2-3-005-slice-acceptance-ticket/v1",
  "ticket_id": "acceptance-ticket-...",
  "acceptance_round_id": "round-...",
  "task_id": "...",
  "producer_run_id": "...",
  "slice_id": "...",
  "slice_revision": "...",
  "question_id": "cq1",
  "question": "...",
  "approved_sources": [{"path": "...", "sha256": "..."}],
  "source_bundle_digest": "sha256",
  "platform_read_scope": {"project_id": "...", "ontology_id": "...", "graph_set_id": "..."},
  "model_state": {
    "project_id": "...",
    "ontology_id": "...",
    "workspace_version": "...",
    "source_signature": "...",
    "build_session_id": "...",
    "graph_set_id": "...",
    "state_digest": "sha256"
  },
  "model_state_digest": "sha256",
  "competency_questions": [{"id": "cq1", "question": "..."}],
  "allowed_read_tools": ["ticket-minimal-tool"],
  "modeling_receipts": [{"stage": "dry-run | apply | readback | validation | reasoning", "status": "validated | applied | complete | succeeded", "receipt_digest": "sha256", "run_id": "...", "project_id": "...", "ontology_id": "...", "slice_revision": "...", "model_state_digest": "sha256", "evidence_ref": {"type": "platform_read", "ref_id": "..."}}],
  "timeout_seconds": 600,
  "quality_standard_ref": "requirements-v2.3#R2.3-005",
  "quality_standard_digest": "sha256",
  "quality_standard_artifact": {"path": "acceptance/standard.json", "digest": "sha256"},
  "unknown_policy": "preserve-explicit-unknown",
  "ticket_revision": 1,
  "ticket_digest": "sha256"
}
```

`schema_version`, `ticket_id`, `producer_run_id`, `acceptance_round_id`, `model_state_digest`,
`source_bundle_digest`, `competency_questions`, `allowed_read_tools`, `modeling_receipts`, and positive `timeout_seconds`
are mandatory canonical ticket fields. The single `question_id`/`question` is the current round projection of the corresponding
entry in `competency_questions`; Runner verifies that the projection is exact. Arrays use canonical
ordering and compact JSON SHA-256; publication is immutable and exclusive-create. To avoid digest
self-reference, `ticket_digest` is computed over a canonical preimage with the top-level
`ticket_digest` and every nested evidence/ref `ticket_digest` field replaced by null; the published
digest is then injected into the immutable ticket and nested evidence refs. Verdict digest uses the
same rule for its own `verdict_digest` field while retaining the already-known ticket digest.

The versioned standard artifact is an immutable, Runner-staged copy of the requirement-owned rubric
(quality checks, CQ policy, unknown policy, and verdict rules) and is included in Acceptance's
ticket/standard projection. Acceptance can read that artifact but cannot edit it; its digest is
required in the ticket, verdict, and evidence. The ticket contains no expected answer, model dialogue, prior verdict, or preset PASS. The
requirement/versioned source corpus owns the standard, approved sources, CQs, generic quality gates,
and unknown policy. Coordinator may freeze and digest those values but may not redefine them.

An allowed source-location hint creates a new ticket revision and may contain only an approved
file/path/document range, section title, business-term aliases/search keywords, or reading/format
instructions. It may not contain an answer, business conclusion, Platform result, or prior wrong
answer.

### Examiner report shape

Each Examiner writes one immutable terminal report before recycle:

```json
{
  "task_id": "...",
  "acceptance_round_id": "...",
  "ticket_digest": "sha256",
  "examiner_kind": "source | platform",
  "child_handle_digest": "sha256",
  "child_session_id": "...",
  "child_input_digest": "sha256",
  "source_bundle_digest": "sha256-or-null",
  "answerability": "answerable | insufficient-evidence | unavailable",
  "conclusion": "...",
  "evidence": [{"ref": "...", "quote_or_fact": "..."}],
  "coverage": {"queries_or_sections": ["..."], "complete": true},
  "gaps": ["..."],
  "model_state": {
    "project_id": "runner-bound",
    "ontology_id": "runner-bound",
    "workspace_version": "runner-bound",
    "source_signature": "runner-bound",
    "build_session_id": "runner-bound",
    "graph_set_id": "runner-bound",
    "state_digest": "sha256"
  },
  "evidence_refs": [{"type": "approved_source | platform_read", "...": "typed fields below"}],
  "report_digest": "sha256"
}
```

Runner accepts a Source report only when `source_bundle_digest` matches the ticket and accepts a
Platform report only when the field is null and the child input digest matches the ticket's platform
projection. Both reports must match task, round, ticket, child handle/session, and model-state
digests. The child payload itself never receives or authors the model-state value: Runner's report
sink adds the complete ticket-bound model-state envelope and digest at ingestion, then computes the
stored report digest. Acceptance receives a report only through `acceptance_child_get_report`; it
cannot read the child report file directly. A report from an old session, different round, different
projection, or recycled handle is a replay and yields `BLOCKED/acceptance-input`.

For missing source evidence, Source Examiner must explicitly say `因缺少相关证据无法回答` and
identify the gap. An unsupported definite answer is not a valid source conclusion. Platform
Examiner must show read scope, query basis, completeness, and evidence/lineage; absence of a fact
must remain distinguishable from a retrieval miss.

Runner normalizes stored evidence to this typed union before Acceptance can read it. An
`approved_source` reference contains `type`, `ref_id`, `ticket_digest`, `source_bundle_digest`,
`location`, `artifact_path`, and `artifact_digest`; its location must be inside an approved ticket
source and the artifact bytes must match. A `platform_read` reference contains `type`, `ref_id`,
`ticket_digest`, `model_state_digest`, `tool`, `request_digest`, `response_digest`, `artifact_path`,
and `page`. `page` contains `ordinal`, `input_cursor`, `output_cursor`, `has_more`, and
`sequence_complete`; non-paged reads use ordinal `0`, null cursors, `has_more=false`, and
`sequence_complete=true`. Paged reads require an unbroken cursor chain and only the final page may
set `sequence_complete=true`. Generic `{ref, quote_or_fact}` child notes remain non-authoritative
explanations and cannot alone support a verdict.

### Verdict envelope

`submit_acceptance_result` accepts only this canonical, exclusive-create envelope; it does not accept
an arbitrary JSON summary:

```json
{
  "schema_version": "r2-3-005-acceptance-verdict/v1",
  "task_id": "...",
  "acceptance_round_id": "...",
  "question_id": "...",
  "slice_id": "...",
  "slice_revision": "...",
  "ticket_id": "...",
  "ticket_digest": "sha256",
  "quality_standard_digest": "sha256",
  "quality_standard_artifact": {"path": "acceptance/standard.json", "digest": "sha256"},
  "model_state": {
    "project_id": "...",
    "ontology_id": "...",
    "workspace_version": "...",
    "source_signature": "...",
    "build_session_id": "...",
    "graph_set_id": "...",
    "state_digest": "sha256"
  },
  "model_state_digest": "sha256",
  "source_bundle_digest": "sha256",
  "modeling_receipts": [{"stage": "dry-run | apply | readback | validation | reasoning", "status": "validated | applied | complete | succeeded", "receipt_digest": "sha256", "run_id": "...", "project_id": "...", "ontology_id": "...", "slice_revision": "...", "model_state_digest": "sha256", "evidence_ref": {"type": "platform_read", "ref_id": "..."}}],
  "source_report_digest": "sha256 | null",
  "platform_report_digest": "sha256 | null",
  "failure_evidence_digests": ["sha256"],
  "infrastructure_failure_digests": ["sha256"],
  "failure_evidence_refs": [{"type": "infrastructure_failure", "failure_digest": "sha256", "cleanup_receipt_digest": "sha256"}],
  "verdict": "PASS | FAIL | BLOCKED",
  "failure_layer": "null | modeling-quality | interview | protocol-delivery | platform | runtime",
  "blocked_reason": "null | acceptance-evidence | acceptance-input | runtime-infrastructure | source-missing | state-invalidated",
  "evidence_refs": [{"type": "approved_source | platform_read", "typed_fields": "..."}],
  "checks": {
    "source_fidelity": "PASS | FAIL | BLOCKED",
    "scope": "PASS | FAIL | BLOCKED",
    "ontology_structure": "PASS | FAIL | BLOCKED",
    "explicit_unknowns": "PASS | FAIL | BLOCKED",
    "validation_reasoning": "PASS | FAIL | BLOCKED",
    "governed_retrieval": "PASS | FAIL | BLOCKED",
    "evidence_lineage": "PASS | FAIL | BLOCKED",
    "competency_questions": "PASS | FAIL | BLOCKED"
  },
  "competency_question_results": [{"id": "...", "status": "PASS | FAIL | BLOCKED", "answer": "...", "evidence_refs": ["typed-reference"]}],
  "recommended_action": "advance | model-repair | retry-after-recovery | revise-ticket | wait | end",
  "summary": "...",
  "verdict_digest": "sha256"
}
```

Runner verifies the exact field set, standard-artifact equality with the ticket, source-bundle equality with the ticket and
Source report, all question/slice/ticket/report/state
bindings (including `ticket_id` equality), typed-union evidence references and page chains, and the rule that PASS has two non-null report digests and null
failure fields. A semantic FAIL and an acceptance-evidence/input BLOCKED require the report digests
that actually exist; a `runtime-infrastructure` BLOCKED may set either report digest to null but must
carry at least one matching `infrastructure_failure_digest` and `failure_evidence_digests` entry. The
infrastructure failure records bind task, round, ticket, child handle/input, attempt and failure
category, so this path has an authoritative result even when no Examiner terminal report exists.
`blocked_reason` is mandatory for BLOCKED and must have at least one `evidence_refs` entry, or for
runtime-infrastructure BLOCKED at least one typed `failure_evidence_refs` entry. The
`infrastructure_failure` reference binds failure digest, cleanup receipt digest, task/round/handle,
attempt, and failure category; it counts as the evidence reference for that blocked reason. A
modeling-quality FAIL cannot carry a BLOCKED reason; an acceptance-evidence/input or
runtime-infrastructure BLOCKED cannot recommend model repair. The stored envelope is the authoritative
result that Coordinator routes; Acceptance cannot replace it with a free-form Team Transport message.
The eight `checks` keys and every `competency_question_results` entry are mandatory and must match
the current round's question IDs. PASS requires all eight checks and every question result to be
PASS with typed evidence. FAIL/BLOCKED must identify the corresponding non-PASS check or question,
use a compatible `failure_layer`/`blocked_reason`, and choose an allowed action; missing or contradictory
checks are `BLOCKED/acceptance-input`, never an implicit PASS.
`modeling_receipts` must contain at least one current-run receipt for each stage `dry-run`, `apply`,
`readback`, `validation`, and `reasoning`; every receipt binds run ID, Project/Ontology, slice
revision, model-state digest, and a typed evidence reference. Ticket and Verdict receipt arrays must
match exactly; a receipt represented only by an external path or a foreign run is not sufficient. Each
receipt must carry a success status appropriate to its stage: `dry-run=validated`, `apply=applied`,
`readback=complete`, and `validation|reasoning=succeeded`; failed, cancelled, pending, or partial
receipts cannot satisfy the modeling gate. Each
receipt's `evidence_ref` is the complete `platform_read` union, not a shorthand: it must include
`type`, `ref_id`, `ticket_digest`, `model_state_digest`, `tool`, `request_digest`, `response_digest`,
`artifact_path`, and the complete `page` object (`ordinal`, `input_cursor`, `output_cursor`,
`has_more`, `sequence_complete`).

Acceptance receives the ticket plus reports and permitted prior-round summaries only. It never gets
raw source files or Platform MCP tools. It first checks report shape, evidence binding, answerability,
and state identity; it then applies the verdict rules below.

## Lifecycle and state machine

```text
PREPARED -> RUNNING
RUNNING -> MODELING_ACTIVE
MODELING_ACTIVE -> WAITING_ACCEPTANCE
WAITING_ACCEPTANCE -> ACCEPTANCE_ROUND_ACTIVE
ACCEPTANCE_ROUND_ACTIVE -> ACCEPTANCE_REPORTS_READY
ACCEPTANCE_REPORTS_READY -> WAITING_ACCEPTANCE   (FAIL/BLOCKED, after child recycle)
ACCEPTANCE_REPORTS_READY -> MODELING_ACTIVE      (FAIL, Coordinator remediation)
ACCEPTANCE_REPORTS_READY -> MODELING_ACTIVE      (next slice after PASS)
ACCEPTANCE_REPORTS_READY -> STATE_REVALIDATION   (before any PASS is consumed)
STATE_REVALIDATION -> ACCEPTANCE_ROUND_ACTIVE   (same digest)
STATE_REVALIDATION -> TICKET_REISSUED           (state drift; invalidate all old PASS)
TICKET_REISSUED -> ACCEPTANCE_ROUND_ACTIVE      (fresh pair for CQ1, then CQ2)
RUNNING -> SETTLED -> CLEANED
```

The Coordinator serializes these transitions. Modeling and Protocol each send a separate
`ready_for_acceptance` and `silent_for_acceptance` message after finishing in-flight work. During
`WAITING_ACCEPTANCE` and `ACCEPTANCE_ROUND_ACTIVE`, Coordinator does not assign another modeling
task. This is a cooperative quiet period, not a Runner-enforced write lock. Acceptance sends its
verdict only to Coordinator; it never instructs Modeling or Protocol directly.

Within a round, Runner starts the two fresh children from the frozen ticket. They may execute in
parallel, but Round 2 cannot start until Round 1's reports, verdict, child cleanup receipt, and
evidence fsync are complete. Acceptance remains the same persistent session for both rounds.

## Verdict and recovery rules

| Condition | Verdict/classification | Coordinator action |
| --- | --- | --- |
| Both reports are evidence-grounded; source answerable and platform agrees; unknowns preserved | `PASS` | advance slice or finish task |
| Platform cannot derive a source-answerable answer, or gives unsupported definitive answer | `FAIL / modeling-quality` | route discrepancy to Modeling/Protocol; revise ontology/content/generic semantic expression; new model revision and fresh round |
| Source material is usable but Source Examiner gives unsupported definite answer | `BLOCKED / acceptance-evidence` | end current round, recycle pair, optionally retry with same ticket or a new ticket containing only a compliant location hint; no ontology repair |
| Approved source truly lacks evidence and Source Examiner says `因缺少相关证据无法回答`; Platform preserves unknown | `PASS` | accept explicit unknown |
| Platform/service unavailable after one identical-input retry | `BLOCKED / runtime-infrastructure` | wait/retry after recovery with a fresh pair |
| Ticket, source digest, question/source binding, or model-state binding invalid | `BLOCKED / acceptance-input` | correct versioned input or wait; new ticket revision and fresh pair |

No unchanged-failure rerun is allowed. Runner has no numeric acceptance-round cap in this increment;
each new round records cause, ticket revision, model state, and result. BLOCKED ends only the current
round: the four persistent roles remain live. A modeling-quality FAIL is not BLOCKED and is routed to
model repair. A fresh semantic modeling start remains under its separate user authorization budget;
R2.3-005 authorizes one real modeling slice only.

The persisted verdict envelope uses the canonical `failure_layer` values
`modeling-quality|interview|protocol-delivery|platform|runtime` for both FAIL and BLOCKED. BLOCKED
also carries a more specific `blocked_reason` such as `acceptance-evidence`, `acceptance-input`, or
`runtime-infrastructure`; this detail never changes the owner map or turns an evidence problem into
PASS. The authoritative verdict is written once through `submit_acceptance_result` with ticket,
round, report, and model-state digests.

## Model-state binding and invalidation

After Modeling and Protocol report ready/silence and before child start, Protocol supplies a
mechanical read-only workspace context/version and modeling-batch/read-model readback; Runner
canonicalizes that receipt with retained Project/Ontology identity and the source/slice revision.
Coordinator freezes the resulting `model_state` envelope without gaining raw platform query access.
Runner records the envelope and digest in the ticket; both Examiners must echo it in their reports.
The final scope cleanup re-reads the same state and records the final workspace context/version as a
post-acceptance consistency check. Acceptance does not wait for cleanup to obtain its input state.
The verdict stores the complete envelope and digest, not merely a human-readable workspace version.

Because the current increment deliberately has no mechanical write freeze, Runner performs a state
revalidation at three boundaries: before accepting each Examiner pair, immediately after each PASS
and before starting the next CQ, and before task settlement. Each revalidation obtains the same
read-only envelope and compares its canonical digest. A mismatch records `state_invalidated`, marks
all PASS results on the old digest unusable, closes/recycles any active pair, and issues a new ticket
revision. Coordinator must then run CQ1 and CQ2 again in order with fresh pairs; results from old and
new digests cannot be combined.

Settlement uses a final `settlement_cas` record containing the expected model-state digest, a monotonic
workspace/version token, and the Runner phase transition. Runner does not emit four-role `settled` or
preserve a PASS handoff until the CAS record and the post-cleanup readback both match. If cleanup
readback detects a later write, it appends `state_invalidated`, withholds settlement, and routes both
CQs through a new ticket revision. This is the strongest current boundary: it prevents a stale PASS
from being declared complete and makes the late-write race observable, while a real-time write reject
between the final read and an external writer remains explicitly deferred hardening.

## Cleanup and evidence

Runner writes append-only, sanitized evidence in the task run directory:

- `roster.json` and Profile/Package/Skill digests;
- `phase-events.jsonl` for assignment, ready/silence, acceptance start, report, verdict, and cleanup;
- `acceptance/<round>/ticket.json`, `source-report.json`, `platform-report.json`, `verdict.json`;
- `acceptance/<round>/child-start.jsonl` and `child-cleanup.jsonl`;
- `model-state/<digest>.json` and a final invalidation record when state changes;
- final four-role terminal results and task settlement evidence.

Evidence records IDs, digests, timestamps, classifications, and cleanup status. It never records raw
credentials, full source contents, hidden prompts, or untrusted child error text. Child cleanup must
be complete before the next round; final task cleanup then stops Acceptance and the other three roles,
completes/cancels every owned Build Session, releases every owned Lease, revokes platform credentials,
and records before/after inventories proving zero active Session/Lease/key residue (or the explicit
retained-scope receipt where non-empty model retention requires it). The task preserves the accepted
non-empty scope only under the existing R2.3-002 retention policy.

## Four-role migration matrix

The migration is an exact contract replacement, not a compatibility layer:

| Existing surface | Required change | Completion evidence |
| --- | --- | --- |
| `ROLE_VALUES`, Profile validation, Package validation | accept exactly Coordinator/Modeling/Protocol/Acceptance for formal tasks; remove source-specialist from formal roster | invalid three-role/extra-role fixtures fail before scope startup |
| `TeamRunner.start()` role lookup and terminal dependencies | derive role IDs and dependency edges from the exact Profile; require Acceptance terminal result in settlement | four-role start/terminal ordering test and no hard-coded “exactly three” path |
| baseline manifest and retained handoff | include Coordinator publish/read-verdict and Acceptance capability/Skill digests and four-role terminal records; project only the existing formal handoff fields | retained handoff schema and cleanup test pass with all capability digests |
| `base-three-agent`, `r2-3-002-t`, source-specialist smoke assets | upgrade formal runnable fixtures to four roles or delete obsolete runnable fixtures; preserve historical evidence files | repository inventory has no runnable formal three-role path |
| `modeling_team/tests`, P2/P2a drivers and launchers | migrate tests that prove shared Runner contracts; remove tests whose premise is the old three-role workflow or mark them archival/non-runnable | full modeling-team test suite passes from clean checkout |
| Codex Adapter runtime cleanup | stop/revoke all four persistent roles plus scoped child records; keep child cleanup idempotent before task cleanup | runtime/core/credential evidence proves zero child residue and four-role settlement |

The migration must be completed before the real semantic start. A test that continues to launch a
three-role Profile is a failed migration, not a backwards-compatibility regression.

## Clean-checkout and repeatability proof

The real acceptance run starts from a dedicated clean clone or temporary worktree at the reviewed
baseline. Before Runner preparation, the Delivery record stores the clone path, commit SHA, exact
`git status --porcelain` output (empty), and a repository file/profile/task manifest digest. Before any
StartLedger reservation, Project/Ontology creation, Session, or Lease, it also captures the inherited
canonical-platform no-start preflight: active `ontology-platform.service`, backend/frontend health,
`SEMANTIC_CANONICAL_STORE=rdf`, `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`,
`SEMANTIC_READ_MODE=canonical`, an authenticated `GET /api/semantic/canonical-mode` response with
HTTP 200 and `product_write_mode=rdf_primary`, and unit/PID/start-time plus process/environment
cross-binding. A mismatch blocks the run without
consuming semantic budget. The run
then proves one complete four-role invocation: prepare, start, semantic start, modeling handoff,
two acceptance rounds, four-role terminal settlement, child cleanup, credential cleanup, and final
scope evidence. This is the only real semantic modeling start authorized by R2.3-005. Any repeatability
check after it must be a no-semantic-start contract/preflight against a second temporary runtime root;
it may validate Profile/Task loading, capability staging, clean startup ordering, and cleanup, but may
not create a Project/Ontology, deliver business input, apply a model, or claim a second real task.
Unrelated dirty files in the developer's main worktree are not silently treated as the clean baseline.

## 2026-08-04 additional three-start authorization

The first R2.3-005 semantic start ended `BLOCKED/collaboration-routing` before the user's grounded
answer reached Modeling and before any complete modeling-quality result. The repaired routing baseline
passed independent deterministic testing. The user now authorizes exactly three additional semantic
starts: cumulative cap four, one consumed, three remaining.

This is a retry budget, not permission to model three more slices. Runs are serialized and stop at the
first accepted end-to-end PASS. A complete modeling-quality failure stops without spending another
start. Only the existing retryable mechanical classifications with
`complete_modeling_quality_result=false` can advance, and each requires an immutable terminal-failure
record plus a tested repair authorization bound to the next clean baseline. A presemantic release does
not consume a start.

The append-only budget boundary is requirement-specific:

- R2.3-005 keeps `.r2-3-005-start-ledger.jsonl`, initial cap one, and an exact `+3` authorization
  tranche for this user decision;
- R2.3-002 keeps its historical filenames, initial cap and exact `+2` tranche unchanged;
- CLI failure classification, repair authorization and budget authorization must select the exact
  requirement ledger through one shared ledger-configuration resolver; no arbitrary filename is
  accepted;
- those three CLI commands expose `--requirement-id`: omission remains the byte-compatible legacy
  R2.3-002 path, while formal R2.3-005 operations must select `R2.3-005` explicitly. Unknown IDs,
  filename/root overrides, and configuration mismatches fail before opening or creating a ledger;
  the formal Runner uses the same canonical repository root and rejects a caller-supplied alternate
  `ledger_root`, while deterministic tests inject a resolver/factory seam for temporary ledgers;
- an authorization can append only when the current tranche is fully consumed, under the existing
  file lock, with unique non-empty authorization ID/reference; forged value, duplicate identity,
  wrong ledger, early authorization and concurrent contenders fail without a partial append;
- budget authorization expands cap only. It cannot substitute for the retryable terminal-failure and
  exact repair-baseline gates checked by the next reservation.

For R2.3-005, management events form a strict append-only state transition under the same lock. A
`terminal_failure` must classify the latest real semantic start; `budget_authorization` must follow
that exact retryable, incomplete-modeling-result failure at an exhausted cap; and the first
`repair_authorization` must follow the newly appended budget event and bind the exact next baseline.
The sole later exception is the existing presemantic rebind contract: when that repair was consumed
by exactly one fresh reservation, the reservation never reached `semantic_start`, it has an immutable
`presemantic_release`, and there is no active reservation, one new non-empty, different baseline
repair may be appended for the same semantic-failed run without another budget event. Concurrent
rebind contenders allow one winner. An interrupted prefix after failure or budget remains valid and
can resume only with its exact next event, but cannot reserve a new start. Wrong order, wrong run,
unused repair, unreleased or started reservation, equal baseline, replay and losing concurrent
contenders leave ledger bytes unchanged.

No live ledger is mutated during implementation or deterministic testing. After a reviewed commit and
independent PASS, Delivery uses `--requirement-id R2.3-005` to append, in the state-machine-enforced
order, the prior run's `collaboration/routing` terminal failure, the user's exact `+3` budget
authorization, and the routing-repair authorization bound to a fresh run baseline.
Every new run still creates fresh scope/roles/credentials and executes the full no-start preflight.

## Implementation sequence

1. Replace the three-role formal Profile/Package contract with the exact four-role contract and
   reject incomplete Profiles; add Acceptance Package, acceptance capability configuration, and the
   basic Platform Examiner Skill.
2. Add non-terminal readiness/silence transport messages and Coordinator phase handling without
   changing terminal settlement semantics.
3. Add Runner-owned acceptance carrier, projected child inputs, opaque handles, child report sink,
   start/recycle lifecycle, read-only key staging/revocation, retry accounting, and sanitized child
   evidence. Keep Codex generic multi-agent features disabled.
4. Make terminal dependencies, retained handoff, baseline manifests, and cleanup derive from the
   exact four-role Profile. Migrate or remove all three-role Tasks, Profiles, tests, and P2 drivers;
   no runnable compatibility path remains.
5. Add the four generic validation/reasoning read MCP wrappers, ticket/report/verdict schemas,
   typed evidence resolver, model-state snapshots and boundary revalidation, PASS invalidation,
   double-CQ rerun routing, and Coordinator recovery routing.
6. From a clean checkout/status-clean worktree run the authenticated canonical-mode no-start preflight
   (including HTTP 200 `product_write_mode=rdf_primary` and unit/PID/env binding), then the deterministic suite, then execute the one real
   four-role task and two real sequential acceptance rounds from the shared test plan.
7. For the 2026-08-04 retry authorization, first land and independently test the requirement-specific
   ledger/CLI configuration, then append failure, `+3` budget and repair-baseline records through the
   reviewed CLI before any fresh reservation. Stop at the first accepted PASS or a complete
   modeling-quality failure.

No frontend UI, database migration, or domain-specific Dify route is required. The four generic
read-only validation/reasoning MCP wrappers are in current scope because the authoritative acceptance
contract requires independent retrieval of Producer-created results; they must reuse existing read
services and remain Project-owned and ontology-scoped.
