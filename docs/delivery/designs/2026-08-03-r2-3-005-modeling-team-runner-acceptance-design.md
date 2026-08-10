# R2.3-005 Modeling Team Runner Acceptance Design

## Status and sources

- Status: Formal Luna-max switch is deterministic-ready; real provider terminal and historical key rotation pending
- Requirement: `docs/requirements/requirements-v2.3.md`, R2.3-005
- Base: R2.3-001 Team Runner/Codex adapter and R2.3-002 fresh-scope modeling workflow
- Delivery record:
  `docs/delivery/records/2026-08-03-r2-3-005-producer-runner-formalization-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-08-03-r2-3-005-modeling-team-runner-acceptance-test-plan.md`

## 2026-08-07 DeepSeek-V4-Flash whole-team runtime retarget

The active R2.3-005 Codex Runtime is retargeted homogeneously to
`deepseek-v4-flash` through DeepSeek's Responses-compatible endpoint. The scope is the exact
four-role Profile (Coordinator, Modeling, Protocol, Acceptance) plus the two private Examiner
processes that Acceptance asks Runner to create. Historical L0/L1/L3 experiment assets are not
changed.

Each Runner-created private Codex home receives an explicit custom provider configuration:
`model = "deepseek-v4-flash"`, `model_provider = "deepseek"`, DeepSeek base URL,
`wire_api = "responses"`, `model_reasoning_effort = "max"`, and an environment-key reference. The API key remains Host-owned: the
adapter resolves `DEEPSEEK_API_KEY` first and otherwise reads the existing gitignored
`backend/.env` `LLM_API_KEY`; it injects the value only into the Codex process environment. The
generated TOML, Agent homes, evidence, logs, argv, repository files, and model-visible shell
environment must not contain the secret.

Both persistent-role and Examiner launch paths pass an explicit minimal process environment rather
than the ambient Host environment. That allowlist contains only `CODEX_HOME`, `HOME`, `PATH`,
`TERM`, locale values, and `DEEPSEEK_API_KEY`. Examiner bubblewrap no longer clears that already
minimal environment; neither namespace puts the key in `--setenv` or any other argv element.
Every generated Codex config sets `shell_environment_policy.inherit = "core"` and excludes
`DEEPSEEK_API_KEY`, so model-launched shell/tool processes do not inherit provider authentication.
The gitignored fallback file must be a regular non-symlink owned by the current user and have no
group/other permission bits; only an exact non-empty `LLM_API_KEY` assignment is accepted.

No Team topology, Task/Package contract, transport, capability, settlement, acceptance,
credential-lifecycle, or platform-access behavior changes. The existing private `auth.json`
staging/cleanup contract is preserved to avoid broadening this retarget into credential-lifecycle
refactoring, but the explicit custom provider authenticates exclusively through the private
DeepSeek environment key. Missing/empty DeepSeek credentials fail before a Codex process is
launched.

The user subsequently authorized resuming R2.3-005 with ten fresh semantic starts. The initial
homogeneous Team uses DeepSeek Flash at `max`. If retained live evidence attributes a workflow-
blocking quality regression to one specific role, that role alone may be retargeted to
`gpt-5.6-luna` at `max` before a later authorized start. Runtime/platform or protocol defects must
not be relabeled as model-quality regressions, and the first complete semantic PASS terminates the
attempt sequence.

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

### Persistent Agent provider-auth boundary

Codex staging keeps platform credentials separate from model-provider credentials. Protocol alone
receives the platform key/config required by its modeling MCP; Acceptance receives no platform,
bootstrap, read, or Protocol key and no source bytes. In the formal R2.3-005 roster only, the
persistent Acceptance Agent receives a private `CODEX_HOME/auth.json` copy containing the host
model-provider credential needed for its own Codex process. This file is staged with the same
regular-file/non-symlink, owner/mode, exclusive-create, `0600`, `O_NOFOLLOW`, and fsync semantics
as other private runtime artifacts, is excluded from Acceptance evidence, and is destroyed during
normal stop/cleanup. Non-formal and R2.3-002 Acceptance paths continue to stage neither provider
auth nor source bytes.

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
that exact retryable, incomplete-modeling-result failure at an exhausted cap. The first
`repair_authorization` follows the newly appended budget event only on that exhausted-cap path; while
cap remains, it follows the repairable failure directly and no budget event is valid. Both paths bind
the exact next baseline.
The sole later exception is the existing presemantic rebind contract: when that repair was consumed
by exactly one fresh reservation, the reservation never reached `semantic_start`, it has an immutable
`presemantic_release`, and there is no active reservation, one new non-empty, different baseline
repair may be appended for the same semantic-failed run without another budget event. Concurrent
rebind contenders allow one winner. An interrupted prefix after failure or budget remains valid and
can resume only with its exact next event, but cannot reserve a new start. Wrong order, wrong run,
unused repair, unreleased or started reservation, equal baseline, replay and losing concurrent
contenders leave ledger bytes unchanged.

### 2026-08-04 R2.3-005 incomplete modeling-quality repair policy

Start8 exposed a candidate-authoring omission and recorded `modeling-quality` with
`complete_modeling_quality_result=false`. That state means no complete semantic result exists; it is
not the completed modeling-quality stop described above. R2.3-005 therefore opts into one additional
repair-eligibility branch while R2.3-002 remains byte- and behavior-compatible.

- `StartLedgerConfig` carries a fixed requirement-owned opt-in, default `false`; only the canonical
  R2.3-005 config enables incomplete modeling-quality repair.
- One shared failure-eligibility predicate accepts the existing mechanical classifications with
  `complete=false`, plus `modeling-quality` with `complete=false` only when that config opt-in is on.
  `authorize_repair`, strict replay, next-start validation and reservation use that same predicate.
- `modeling-quality` with `complete=true`, any complete semantic result, missing independent repair,
  stale/equal baseline, exhausted cap, active reservation, wrong gate binding or wrong event order
  remains terminal and fails without mutation.
- Budget authorization does not use the new predicate. It remains restricted to the existing
  retryable mechanical classifications at an exhausted cap, so incomplete modeling quality cannot
  expand cap or substitute for explicit user authorization.
- Existing tests cover R2.3-005 incomplete-modeling repair/replay/reservation and complete=true
  rejection, fresh-baseline/order/gate/serialization failures, CLI selection, and unchanged
  R2.3-002 modeling-quality rejection. One test replays the retained `10/8/0` event shape and proves
  direct failure-to-repair-to-reservation without a budget event. No start8-specific branch or
  alternate ledger is introduced.

No live ledger is mutated during implementation or deterministic testing. On the historical initial
exhausted-cap authorization, Delivery used `--requirement-id R2.3-005` to append, in the
state-machine-enforced order, the prior run's `collaboration/routing` terminal failure, the user's
exact `+3` budget authorization, and the routing-repair authorization bound to a fresh run baseline.
For the retained start8 state at cap/count `10/8`, Delivery instead appends direct
failure-to-repair authorization with no new budget event.
Every new run still creates fresh scope/roles/credentials and executes the full no-start preflight.

## 2026-08-05 explicit one-start authorization

After start13 stopped at the Protocol candidate handoff, the user explicitly authorized one fresh semantic
start. This is still a retry of the same simple `C -> B -> A` slice, not permission to create another slice.
The isolated formal ledger state is `cap/count/active=13/13/0`; the authorization must extend it to `14/13/0`,
and the first complete modeling-quality PASS still ends the run immediately.

The formal R2.3-005 policy keeps `authorization_increment=3` as the coordination default. A caller that has an
explicit user quantity may persist any positive integer `additional_starts`; this turn passes `1`. `bool`, zero,
negative, non-integer, duplicate, out-of-order, and losing concurrent records fail before append. Strict replay and
`_start_cap` add the stored amount from each authorization record, so retained historical `+3` records replay
unchanged while the new `+1` record yields `13 -> 14`. R2.3-002 remains the exact `+2` policy and its ledger bytes
and behavior are unchanged. Coordination without an explicit user quantity continues to pass `3`; the CLI does not
silently create a budget event by omitting the amount.

Implementation and tests use only injected temporary ledgers. Delivery may append the one formal `+1` event to the
canonical ledger only after this narrow change has an independent PASS and a clean committed baseline.

## 2026-08-05 start15 exact-candidate redrive repair

Start14 proved that the bounded redrive terminates and cleans up, but its reminder-only payload did not let Protocol
recover the immutable candidate. Protocol returned a free-text resend request, then the redrive turn made no
mechanics or platform call. The next repair changes only the formal R2.3-005 redrive delivery:

- retain the exact original candidate `text` and its original Runtime delivery metadata when the first formal
  candidate is recognized;
- after the bound candidate turn completes without a valid receipt or conflict, send one direct
  `kind=candidate-redrive` Runtime delivery on the same Protocol thread whose `text`, `sender_id`, `recipient_id`,
  `delivery_id`, `expects_reply`, and `reply_to_delivery_id` are byte/value-identical to the original candidate;
- when Protocol has already occupied or acknowledged the original request's reply slot with a response that the
  formal candidate validator rejects, Runner may ask the Broker for one formal-only compare-and-swap reopen. The
  Broker must verify the original request, the exact invalid reply delivery, reversed participants, and the unused
  replacement allowance before restoring that original reply binding; immutable delivery history is not removed;
- treat that delivery as mechanical redelivery, not a second Team Transport record, candidate revision, semantic
  start, or permission to merge history. Protocol must pass its `text` unchanged to `build_candidate_receipt` and
  reply to the original `delivery_id`; a real translation problem uses the existing exact conflict builder;
- keep the existing one-redrive limit, exact turn-start/completion barrier, deadlines, terminal latches, cleanup,
  and formal-only gate. R2.3-002, schema-v1, ordinary schema-v2, and the Modeling candidate are unchanged.

The user authorized exactly one additional semantic start and explicitly waived the normal plan-review and independent
test gates for this exceptional retry. The canonical ledger remains `14/14/0` until luna-max delegated development,
focused developer smoke checks, and a clean commit. Only then may Delivery append `+1`, authorize start14 repair
against the new baseline, and launch start15 as the acceptance test.

## 2026-08-05 recoverable issue escalation

Start15 proved exact redelivery but exposed a Protocol interpretation problem that should have been recoverable in the
same Team run. The user paused further semantic attempts and promoted the following formal-only capability into current
minimal scope. This section supersedes the earlier future-productization deferral for pause/resume, but only for this
bounded cooperative intervention path.

### Functional flow

1. Any persistent role may call a native Team Transport `report_issue` with fixed category, summary, failing operation,
   error, mutation state, and requested action. Broker assigns the immutable issue ID and routes the structured record
   to Coordinator; it is not a `TaskResult` and never settles the reporter.
2. Coordinator sends a bound `pause` issue-control message to the reporter. No Runtime interrupt occurs. The reporter
   obeys the instruction by stopping new tools/messages/terminal reporting and ending its current turn. Runner records
   `WAITING_OWNER` or `WAITING_REPAIR`, freezes candidate active-time accounting, redrive, settlement, and cleanup, and
   retains the Project/Ontology, Session/Lease, credentials, process/thread, transport, candidate, and isolated files.
3. Runner emits one structured outer issue event. Outer guidance or a repair-completed record is persisted before it is
   delivered to Coordinator. Coordinator then sends one bound `resume` control containing the exact resolution to the
   reporter. A live Codex Agent continues with a new turn on the same thread; no `prepare`, `start`, reservation,
   repair authorization, budget event, or `semantic_start` occurs.
4. `abort` remains explicit and terminal. A dead process/thread, unresolved write uncertainty, binding drift, or a
   component that cannot be rebound safely must fail closed instead of fabricating continuation.

### Control and evidence contract

- One active issue per run. State is `reported -> pause_sent -> waiting_owner|waiting_repair -> resolution_ready ->
  resume_sent -> resolved`, or `aborted|rebind_required`. Every transition is CAS-bound to run, issue, reporter,
  Coordinator, active thread, candidate identity when present, and a single-use control epoch.
- Pending issue rejects role terminal reports. It does not interrupt an active turn; Broker callbacks only enqueue the
  issue and return, avoiding Runtime/Broker lock inversion. Runner main-loop processing performs evidence writes and
  Runtime delivery after App Server I/O locks are released.
- Formal candidate deadlines use active time. Issue waiting time cannot trigger timeout, automatic redrive, terminal
  latch, settlement, or cleanup. Existing delivery/reply slots and immutable history remain intact.
- Outer resolution types are `guidance`, `repair_completed`, and `abort`. Platform repair records component, before/
  after baseline or component digest, verification reference, and state reconciliation. Unknown or uncertain writes
  cannot resume without formal receipt/readback reconciliation.
- Role source and runtime file isolation remain unchanged. Shared service/data repair may resume after health and state
  verification. For `ontology_platform` MCP code, Host may create a versioned isolated snapshot and explicitly reload
  the MCP while retaining the App Server and thread; exact tool-surface revalidation and rollback are mandatory. Frozen
  Protocol mechanics/assets, instructions, Transport/Runner code, or dead App Servers are `rebind_required` in this
  increment. The current minimal implementation supports in-place resume only for verified
  `shared_backend_service|shared_backend_data` repairs; it deliberately classifies `ontology_platform` MCP replacement
  as `rebind_required` until the versioned reload/revalidation path exists.

### Non-goals

No hard `turn/interrupt`, automatic remediation, arbitrary shell/systemd access for Team Agents, persistent database
queue, multi-issue scheduler, cross-process thread resurrection, cross-run recovery, semantic answer invention, or new
semantic-start authorization is added. Existing manual pause remains legacy and is not used by this flow.

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
7. For the historical exhausted-cap 2026-08-04 retry authorization, first land and independently test
   the requirement-specific ledger/CLI configuration, then append failure, `+3` budget and repair
   through the reviewed CLI. For any later repair while cap remains, append failure then repair with
   no budget event. Stop at the first accepted PASS or a complete modeling-quality result.

No frontend UI, database migration, or domain-specific Dify route is required. The four generic
read-only validation/reasoning MCP wrappers are in current scope because the authoritative acceptance
contract requires independent retrieval of Producer-created results; they must reuse existing read
services and remain Project-owned and ontology-scoped.

## 2026-08-06 amendment: Host-derived Acceptance child input

This amendment supersedes only the argument-ownership semantics of the historical
`acceptance_child_start(..., input_ref, input_digest, ...)` signature above. It does not rewrite the historical design
record and does not change child isolation, ticket identity, attempt/recycle, report, verdict, or settlement rules.

In the current contract, `input_ref` and `input_digest` are optional compatibility arguments. Common Runner dispatch
uses `round_id` and `kind` to call the existing `RunnerAcceptanceCarrier.project_child_input` and supplies the
canonical pair when the caller omits them. Acceptance prompts, Tasks, and Skills must direct the Agent to omit both;
the Agent must never construct a projection, hash it, or substitute `ticket_digest`.

An exact legacy caller may still supply both arguments, but Runner compares them with the Host-derived canonical pair.
Supplying only one, supplying a wrong digest or projection, or reusing a projection across kind or round fails closed.
The capability endpoint schema keeps `required ⊆ arguments ⊆ properties` and rejects unknown arguments. The real
start38 CQ1 fixture binds source digest
`b2577d6e649c8593087a518754ef510a4f4f49b0f3171f3f3daf2a92b4a0cacc` and platform digest
`2926d748a84333ea115f1564d6b289f7c6f3214dfcce00f5797a9819ab2927f5`.

Implementation impact is LOW. Verification passed **63 focused tests plus 21 subtests**, complete modeling regression
**483 passed, 1 skipped, 195 subtests**, Ruff, and diff checks. This amendment remains pending independent final review;
it is not yet a start39 release gate PASS.

Independent final review subsequently passed. Omitted Host-derived arguments and the exact explicit legacy pair are
reachable; partial, wrong, cross-round, cross-kind, and unknown-argument forms fail closed. Existing `start_child`
ticket/capability validation, replay, lifecycle, report/recycle, and settlement contracts remain unchanged, and the
amendment introduces no Runtime or Pi coupling. The amendment is eligible for commit and presents no remaining
start39 blocker.

### 2026-08-07 — Start40 retained upstream proof and failed in Acceptance runtime

Start40 reused the nearest accepted r3 candidate through the corrected direct PTY. Candidate publication, platform
application/validation/reasoning, governed retrieval, and handoff completed in a fresh scope and remain valid upstream
evidence; the later runtime failure must not trigger remodeling. Host-derived omitted input binding worked. Source
attempts 0 and 1 then produced typed `child-timeout` failures and were recycled to zero residue; platform start failed
before handle/read-key creation, so no typed platform child result permits retry.

The first recycle exposed a prompt defect: `completion_ref` is a discriminated one-key digest reference, never the
readiness object. Commit `8efe993` makes that rule durable in Acceptance instructions, Task text, capability
schema/dispatch, packaged Skill, and regression coverage. It is reusable protocol guidance, not a start-specific
checker.

The user chose terminal failure rather than continued verdict-contract repair. Issue 2 used formal abort; Runner
destroyed child/role credentials and processes, revoked all keys, terminalized Session/Lease, and retained the
non-empty failed-written Project. No CQ verdict or settlement is inferred. Classification is
`runtime/infrastructure`, `complete_modeling_quality_result=false`; ledger replay is `40/39/0`, leaving one idle
authorized start and no authorization for repair or start41.

## 2026-08-07 amendment: Runner-bound Examiner report submission

Start44 reached the first independent Source Examiner after completing candidate publication, platform
application, validation, reasoning, and governed retrieval. The retained child rollout at
`acceptance-carrier/acceptance/acceptance-round-r23005-real-20260807-deepseek-start44-cq-001-1/children/
8f16a8f8c3a51c9be5ab7f9ab0db6aa5cdca8e34cbd770ea85f2976c250c84b2/home/sessions/2026/08/06/
rollout-2026-08-06T18-55-02-019fd86d-cdb1-7dc0-aac9-b2884a8731e3.jsonl` records the correct Version 2 /
`quality_rating:number` reasoning at `18:55:26.047Z`, followed by `submit_examiner_report` arguments `{}` at
`18:55:26.399Z` and no call output. The model-visible tool schema exposed only an unconstrained empty object, so
this is a confirmed prompt/tool contract defect. Separately, the persistent Acceptance Agent's later polling turn
ended with provider `402 Payment Required: Insufficient Balance`; that runtime/provider failure does not erase the
earlier child evidence and must be reported independently rather than attributed to the report schema.

The durable repair keeps the stored Examiner report shape above unchanged while making ownership explicit:

- the child submits only `answerability`, `conclusion`, `evidence`, `coverage`, `gaps`, and kind-specific
  evidence locators/receipts;
- the private Runner report sink injects `task_id`, `acceptance_round_id`, `ticket_digest`, `examiner_kind`,
  `child_handle_digest`, `child_session_id`, `child_input_digest`, `source_bundle_digest`, and the complete
  ticket-bound `model_state`, then computes `report_digest`;
- the Host callback behind `ReportSinkServer` applies the same strict kind-specific child-payload validator and
  normalization before any injection or persistence. The MCP bridge schema is guidance, not the trust boundary;
  a child that bypasses the bridge and writes directly to its mounted private socket cannot submit extra
  Runner-owned fields or a cross-kind shape;
- Source child evidence locators contain only approved `location` values. Runner resolves each location against the
  staged ticket manifest and mechanically constructs `ref_id`, `ticket_digest`, `source_bundle_digest`, the exact
  round-bound retained `artifact_path`, and that source entry's per-file `sha256` as `artifact_digest`; an unknown,
  duplicate, or out-of-manifest location fails closed;
- Platform child evidence locators contain only `ref_id`, `tool`, `request_digest`, `response_digest`,
  `artifact_path`, and the structurally validated pagination/completeness `page`. Runner first matches the immutable
  tool/digest/path tuple to exactly one receipt in this child's scoped proxy registry, rejects duplicates, and only
  then injects `type=platform_read`, `ticket_digest`, and `model_state_digest`. The child schema forbids those
  Runner-owned binding fields, so a child cannot ask Runner to relabel a foreign receipt;
- the MCP tool publishes strict kind-specific JSON Schemas for all child-authored fields and rejects unknown or
  missing fields. The Runtime starts the private sink bridge with a non-secret `--kind source|platform` argument,
  and the bridge selects only that kind's frozen schema. Source instructions describe location-only submission and
  Runner constructs its deterministic `ref_id`; Platform instructions require exact proxy-locator copying without
  invention;
- top-level `source_bundle_digest` injection is kind-specific: Source receives the immutable ticket value and
  Platform receives `null`;
- the Platform Examiner binds both its report sink and read proxy under the already-created short, private
  `/tmp/mt-ex-<handle-digest-prefix>` socket root when the durable child path exceeds Unix-domain socket limits;
  the child still sees only its bind-mounted `/agent/home/*.sock` endpoints, and teardown removes the short root.

No ticket, verdict, semantic model, platform read allowlist, retry budget, or settlement rule changes. Invalid
child payloads still fail closed before durable report publication. Focused tests must prove schema discovery,
Runner binding injection, rejection of missing/extra child fields, mechanical per-file Source reference creation,
exact Platform proxy-receipt matching, kind-specific source-bundle handling, both Examiner launch paths on DeepSeek
Flash/max (including a durable child path longer than the Unix socket limit), and unchanged full-report
validation/replay behavior. Independent review and
verification are required before start45; start44 is recorded as `collaboration/routing,false` and consumes the
fourth of the ten newly authorized starts.

## 2026-08-07 amendment: Examiner child stdout pump and package-specific elicitation allowlist

Start45 carried the proven r3 candidate through candidate publication, the five atomic platform batches,
readback, validation, reasoning, the governed retrieval gate, and the formal `delivery-5` acceptance-stage
handoff, then reached the first real Source Examiner. The retained rollout records a correct six-field
`submit_examiner_report` function call, but no function-call output ever returned: the Examiner App Server's
stdout was never consumed after `turn/start`, the private report bridge never reached `report.sock`, the Host
received no Source report, and the 600-second child watchdog classified the run as `runtime/child-timeout`
(`runtime/infrastructure`, `complete_modeling_quality_result=false`). DeepSeek Flash/max/Responses stayed
homogeneous and reachable across all six runtime paths; the failure is a Runtime output-consumption gap, not a
modeling-quality or provider defect.

Two layers must be repaired together; either alone still fails the Examiner:

1. After `CodexRuntimeAdapter._launch_acceptance_child_impl` returns from `turn/start`, no path consumes the
   Examiner child's App Server stdout. The child `_Agent` is a method-local object that is intentionally not
   registered in `self.agents`, so the `receive_messages` and `terminal_report_blocked` drains never cover it.
   The model's `submit_examiner_report` elicitation therefore blocks forever inside the App Server.
2. `CodexRuntimeAdapter._notification`'s elicitation allowlist admits only Team Transport, the two Protocol
   surfaces, and Runner Capability. It has no branch for `examiner_report` or `platform_read_proxy`, so even a
   consumed Examiner notification would be declined.

### Non-goals

This amendment is a platform/Runtime narrow repair only. It does not remodel the proven r3 candidate, change
platform semantics, alter the strict six-field report contract, or touch ticket/verdict/retry/settlement rules.
It does not change command approval (the built-in decision stays `decline`), the four existing elicitation
branches, or the output-consumption and elicitation behavior of the four persistent roles. It introduces no
Runner phase gate, write freeze, Lease revocation, pause/resume state, or Producer-side abstraction, and it
consumes no semantic start. Start46 remains gated on an independently passed repair, a reviewed clean baseline,
and exact repair authorization.

### Repair contract

- **Examiner child output pump.** After `turn/start` succeeds and before the resource is returned, the Runtime
  starts one lifecycle-owned daemon thread (alongside the existing watchdog) that owns the Examiner child's
  stdout. The pump reuses the existing `_read_output_line` and the child `_Agent`'s reentrant `io_lock` — the
  same primitives `_rpc_locked` already serializes on — and dispatches each parsed notification line through
  `adapter._notification`. No new read path is introduced. The child `_Agent` reference (process, stdout,
  `io_lock`, `stdout_buffer`) is retained on `_CodexChildResource` so the pump shares the exact lock instance
  any future reader must honor.
- **Fixed failure semantics.** `_read_output_line` raises on App Server output close; the pump catches that and
  any malformed line or process death and routes them only through the existing `_record_failure` with a fixed
  `runtime` reason code, honoring its `_failure_recorded/_stopped/_destroyed` guards. No path retains or
  surfaces raw exception text, and a pump exit after the watchdog fires or `stop` is requested is not a failure.
- **Pump lifecycle.** The pump is stopped and joined with a timeout inside `_CodexChildResource.stop`, before
  `_terminate_process`, proxy, and report-sink teardown, so it never reads a closed descriptor. `destroy`
  ordering is otherwise unchanged; zero thread/process/socket residue after stop/destroy is an acceptance gate.
- **Package-specific elicitation allowlist.** The new branch keys on `agent.package.package_id` — not on role,
  because both Examiner packages carry role `source-specialist` — matching the package discrimination already
  used by `_require_expected_mcp_servers`. The Source Examiner package admits only `examiner_report`; the
  Platform Examiner package admits `examiner_report` and `platform_read_proxy`. Every other package and role,
  including the four persistent roles, continues to fail closed exactly as today, and built-in command approval
  keeps returning `decline`.
- **Concurrency boundary.** The pump reads stdout while `ReportSinkServer` reads `report.sock`; they are
  independent threads on independent descriptors and share no state. The pump and any server-request response
  write serialize on the same child `io_lock`. Per-child socket-root isolation is unchanged and the pump never
  touches a socket.

### Impact and risk

GitNexus upstream impact, recomputed this session: `_CodexChildResource` MEDIUM (6 direct callers, no affected
process), `_notification` CRITICAL (163 upstream, 5 processes), `_launch_acceptance_child_impl` CRITICAL
(187 upstream, 8 processes). Every affected process is a Runtime call-chain entry (smoke, protocol drivers,
ledger, `__main__`, semantic MCP tools); none is a modeling-semantic path. The change is therefore treated as a
high-risk shared-Runtime edit: the elicitation addition is a package-specific branch that leaves every existing
allowlist arm and command-approval behavior unchanged, and the pump is scoped to the Examiner child, with
persistent-role output handling untouched.

### Acceptance focus

Focused tests must prove: the exact allowlist matrix (Source admits `examiner_report`; Platform admits
`examiner_report` and `platform_read_proxy`; every other package/role, including `source-specialist` outside the
two Examiner packages, declines; command approval stays `decline`; the four existing arms are unchanged); a
scripted App Server that emits an elicitation notification after `turn/start` returns is drained by the pump,
reaches `_notification`, and is published to `report.sock` as a six-field payload; EOF/malformed/process-death
map to the fixed `runtime` reason with no raw exception text and honor the `_record_failure` guards without
overwriting an already-delivered report; stop/destroy leave zero thread/process/socket residue and join the pump
before descriptor teardown; the existing start44 contract tests, Codex isolation tests, homogeneous DeepSeek
Flash/max/Responses across all six runtime paths, and no-secret static probes still pass; and the full
`modeling_team/tests` suite passes except, at most, the known historical P2a byte-freeze hash assertion, which
is reported as-is and never satisfied by editing the frozen expectation.

Independent review and verification are required before any start46 reservation; this amendment consumes no
semantic start. Start45's terminal failure stays recorded as `runtime/infrastructure,false` and is the fifth of
the ten newly authorized starts, leaving five; repair authorization for start45 may be written only after this
amendment is independently accepted and committed on a reviewed clean baseline.

## 2026-08-09 Start68 sequential-CQ Coordinator contract repair

### Evidence and target

Start68 reached the first complete independent verdict route: cq-001 was submitted and confirmed as `PASS`.
`AcceptancePhase.route_verdict` then correctly returned the same generation to `WAITING_ACCEPTANCE`, preserving
the already completed Modeling-ready and Protocol-silent signals so a second sequential round was legal. The
Coordinator nevertheless stated that it would wait for cq-002's verdict without sending cq-002
`acceptance_start`; no second round existed, so both persistent roles waited until the run was aborted.

The target behavior is requirement-owned Coordinator scheduling: after it receives and confirms a PASS verdict,
it inspects the frozen question order already injected by the Runner and starts the next published,
not-yet-completed ticket with that ticket's exact `acceptance_round_id`. After the final frozen question PASS it
starts no further round and waits for the normal Acceptance terminal handoff and settlement sequence.

### Current minimal scope

- Amend the authoritative Coordinator package instructions and the formal Coordinator branch of
  `TeamRunner._task_text` with the same explicit state transition: PASS plus a remaining frozen question means
  immediately send exactly one `acceptance_start` for the next published ticket; do not merely wait for a verdict
  that cannot exist.
- Preserve requirement order (`cq-001`, then `cq-002`), the existing ticket objects, ticket revisions,
  `acceptance_round_id` values, Team Transport operation, and current generation. Coordinator must not rebuild,
  mutate, or republish a ticket while advancing.
- Advance only after the prior verdict has been received through the normal verdict route and confirmed through
  the existing Runner-private verdict capability. FAIL returns to Modeling repair under the existing generation
  rules; BLOCKED waits for recovery/revision; neither starts the next CQ. A final PASS starts no extra CQ.
- Before the formal Runner lets `CoordinatorPhaseController` change phase or lets Team Transport enqueue an
  `acceptance_start`, it asks the existing `RunnerAcceptanceCarrier` to validate the Coordinator-selected round.
  Validation is read-only and must require: the round has an already published frozen ticket; its question is the
  next requirement-ordered CQ without a completed usable PASS; the selected round has not already started/completed;
  and no next round exists after the final CQ PASS. Before cq-002 starts, the validator invokes the existing passive
  `revalidate_model_state` boundary against the live platform snapshot, then requires cq-001's verdict to remain
  `verdict_usable=true`, its ticket/round epoch and model-state digest to equal the carrier's current bound state,
  and its child pair to be fully recycled with no active handles. The cq-002 ticket must bind that same current model
  state. A wrong/early/replayed/post-final ID leaves phase, generation, delivery queue, tickets, rounds, and verdict
  state unchanged. A real platform drift may append only the existing state-revalidation/invalidation evidence and
  invalidate stale PASS/round state as designed; it still must not change coordination phase or enqueue a delivery.
- The Host continues to reject overlap, stale generations, out-of-phase starts, and now wrong/unpublished,
  early, duplicate, or post-final round IDs. The carrier validation must not return or choose a round ID and must
  not start anything; Coordinator remains the sole CQ selector. No new Host scheduler, persistent state field,
  model-visible capability, or automatic runtime delivery is introduced.

### Non-goals

This repair does not change Acceptance semantics, verdict construction, Examiner inputs or reports, the proven r3
candidate, platform apply/retrieval, settlement, cleanup, start-ledger policy, provider configuration, or outer
input. It does not add another competency question, business slice, retry loop, generalized orchestration layer,
or product UI. It consumes no semantic start during implementation or deterministic verification.

### Risk containment

GitNexus reports `TeamRunner._task_text`, `TeamRunner._coordination_phase_callback`, and
`CoordinatorPhaseController.start_acceptance_round` as CRITICAL (each 83 affected symbols, 77 direct dependants)
because they are shared prompt/coordination entry points. The implementation must therefore change only the existing
formal Coordinator prompt branch and insert the carrier validation only in the formal R2.3-005 callback before the
unchanged generic phase transition. The generic phase controller, non-formal runs, other roles, branch selection,
and legacy tasks remain unchanged. Focused tests freeze both the positive formal behavior and negative unaffected
surfaces.

### Acceptance criteria

1. Both authoritative Coordinator prompt surfaces explicitly require cq-001 PASS -> cq-002 `acceptance_start`
   using the already published cq-002 round ID, and explicitly forbid waiting for cq-002 verdict before starting it.
2. The prompt contract says final-CQ PASS starts no further round; FAIL and BLOCKED do not advance; two rounds are
   never active concurrently; ticket rebuild/republication is forbidden during advancement.
3. Runner+carrier integration tests prove PASS returns to `WAITING_ACCEPTANCE` on the same generation and permits
   exactly the next published frozen round. Wrong/unpublished ID, cq-002 before cq-001 PASS, duplicate/replayed
   round, third round, and any start after final PASS fail before phase transition and enqueue, with carrier and
   delivery state unchanged. A valid-looking cq-002 start after post-PASS platform drift performs passive state
   revalidation, invalidates cq-001 PASS, rejects the start with no phase/enqueue change, and requires fresh tickets
   plus both CQs on the new state. Existing overlap, stale generation, FAIL, and BLOCKED behavior remains unchanged.
4. The carrier validator never selects or starts a round and is not exposed as a model-visible capability. The
   generic `CoordinatorPhaseController` and non-formal coordination behavior remain unchanged.
5. Formal Coordinator task text contains the repair; other roles and non-formal task text remain unchanged.
6. Focused and full `modeling_team/tests`, Ruff, GitNexus `detect_changes`, service restart, backend health, and
   frontend HTTP verification pass before commit. This proves implementation readiness only; R2.3-005 still
   requires a newly authorized real start completing cq-001, cq-002, terminal reports, settlement, and cleanup.

### Implementation and independent verification result

Implemented as reviewed. `RunnerAcceptanceCarrier.validate_coordinator_acceptance_start` validates only the
Coordinator-selected round and returns no selection; the formal Runner callback calls it before the unchanged generic
phase controller. Both Coordinator prompt surfaces carry the sequential PASS contract. A focused six-test module
covers the ordered success path, wrong/early/replayed/stale/third-round rejection, current digest and child cleanup,
post-PASS state drift invalidation, and role isolation.

Independent Round 7 found no behavior defect but failed the planned full-Ruff gate on one pre-existing unused local in
the FIFO test. The one-line lint repair did not alter behavior. Independent Round 8 passed full Ruff, FIFO 10/10,
focused sequential-CQ 6/6, R2.3-005 172/172 with one opt-in skip, related 66/66, complete modeling-team unittest
discovery 488/488 with one opt-in skip, diff/GitNexus checks, service restart, backend health, and frontend HTTP 200.
No real semantic run occurred; the live completion gate remains open.
## 2026-08-09 start69 live prompt repair

start69 reused the frozen r3 continuation candidate and correctly crossed the formal candidate-receipt barrier, but
the Protocol Agent then followed the shared package's unconditional sentence that called the current work a
"capability smoke task". It performed only the permitted health read, returned that result to Modeling, and attempted
terminal reporting. The Host rejected the attempt as `missing_modeling_handoff`; no platform stages, governed
retrieval, acceptance handoff, or CQ round occurred. This is a prompt-contract defect in the Protocol package, not a
modeling-quality result and not a failure of the sequential-CQ Host validator.

The narrow repair makes task-mode selection explicit. The smoke-only health/terminal path is available only when the
loaded Task/Profile itself declares capability smoke; availability of a health tool, a candidate receipt, shared
package text, or supplemental input cannot imply that mode. For `task_id=r2-3-005-formal-acceptance`, receipt and
health are intermediate evidence only. Protocol must execute the five current-run platform stages, complete governed
retrieval, publish the Coordinator handoff, send Modeling's bound gate-complete notice, send
`silent_for_acceptance`, and wait for the Runner's Protocol `terminal-handoff` before terminal reporting.

This repair changes no Host selector, phase state, ticket binding, platform API, or semantic model. A prompt-contract
test binds the formal task ID and non-smoke objective to the mandatory full-run wording. Independent Round 9 is the
deterministic repair gate; only a later fresh live start can prove the repaired behavior.

## 2026-08-09 start70 terminal-chain and verdict-shape repair

Start70 reached both ordered CQ `PASS` verdicts and Acceptance settlement, then exposed a lifecycle dependency gap.
The pre-repair graph required Protocol to wait for Modeling and Coordinator to wait for Modeling, Protocol, and
Acceptance, but no settled role could send Modeling its explicit terminal handoff. Modeling could not report early:
doing so would make it immutable and unable to receive later FAIL/BLOCKED revision work.

The minimal design adds one edge only when `formal_coordination` is active:
`modeling <- acceptance`. Acceptance remains terminal-guarded by final settlement, so FAIL/BLOCKED and unfinished
rounds emit no Modeling terminal handoff. After final settlement, the existing broker/drain machinery produces the
chain Acceptance -> Modeling -> Protocol -> Coordinator without a new lifecycle state or model-visible capability.
All non-formal dependency maps are unchanged.

Start70 also showed that the Acceptance Agent could confuse Examiner answerability labels with CQ verdict status.
The authoritative package now requires each CQ result to contain only `status`, `answer`, and `evidence_ref_ids`, with
status exactly `PASS`, `FAIL`, or `BLOCKED`; `answerable`, `unanswerable`, `insufficient-evidence`, and `unavailable`
are never CQ statuses. Mechanical carrier tests reject those values before verdict/round mutation. A real
`TeamRunner.prepare/start` integration test freezes both the formal added edge and the unchanged non-formal graph.

Plan review initially rejected early Modeling termination because it destroyed revision reachability, then passed the
formal-only dependency design after it preserved FAIL/BLOCKED lifecycle and non-formal compatibility. This repair is
an implementation gate only; start71 remains the sole authorized live proof of full terminal settlement.

## 2026-08-09 start71 Acceptance terminal-report closure

Start71 proved the terminal dependency edge itself was not sufficient: after final PASS and settlement, Acceptance
sent an ordinary completion delivery but never called the terminal tool, so the edge had no source result. The formal
Acceptance task-text branch had replaced the generic terminal instruction, while the package's wait language made the
ordinary delivery a plausible completion action.

The repair has two coordinated parts. First, the package and formal task text explicitly distinguish a verdict route
or completion delivery from `report_task_result`. Non-final cq-001 PASS and every FAIL/BLOCKED path remain live. Only
after final cq-002 usable PASS is submitted and routed does Acceptance call
`report_task_result(status=completed)` exactly once. Second, the formal Acceptance terminal guard accepts only
`completed` and invokes the existing settlement finalizer before checking settlement, so Agent timing cannot race the
foreground drain.

Because Broker report handling and foreground drain are concurrent, the finalizer is protected by one Runner-owned
lock and rechecks settled/readiness inside the lock. Both callers share this idempotent path. Exactly one settlement
CAS, settlement artifact, and Runner evidence record may be written; the other caller observes the settled result.
Missing prerequisites or non-completed Acceptance status remain rejected without a terminal result or handoff.
The plan passed review only after adding this serialization and completed-only guard.

No semantic start is part of this repair. The start69–start71 authorization is exhausted, and a later live terminal
proof requires new user authorization after deterministic PASS and commit.

Implementation matches the reviewed design. Independent Round 12 passed the true concurrent finalization test,
completed-only rejection/acceptance boundary, one Acceptance-to-Modeling handoff, direct four-role terminal order,
actual formal/non-formal Runner graph and prompt contract, full requirement/modeling-team regressions, modeling-team
Ruff, diff/GitNexus checks, and restarted backend/frontend health. No live start was performed.

## 2026-08-10 formal-only Luna-max runtime and provider-failure boundary

The post-start72 runtime target is a formal-only six-package manifest, not shared package mutation. The authoritative
artifact maps Coordinator, Modeling, Protocol, Acceptance, Source Examiner, and Platform Examiner to the exact tuple
`gpt-5.6-luna/openai/max`. `TeamRunner.prepare` validates and digest-binds it before platform preflight, ledger,
run-root, transport, capability, or process creation. The initial and post-preflight baseline digests must both equal
the loader digest. Non-formal and R2.3-002 package behavior remains unchanged.

Formal Codex processes never resolve or inherit the historical DeepSeek key. Host OpenAI auth must be a regular,
non-symlink, owner-only file and is staged through an exclusive fsynced 0600 copy. It remains available through
initialize, thread start, exact MCP discovery, and synchronous acceptance of the first turn, then is unlinked before
any model-selected ServerRequest/tool/MCP dispatch. Ordinary early notifications buffer; an early request with an
`id` first removes auth and receives a typed response before the matching turn response is awaited. Both persistent
and Examiner paths share this barrier and secret audit, including `.sh` and extensionless shell snapshots plus
session/SQLite/WAL/SHM artifacts.

Current Codex status uses opaque tool-map keys, so exact MCP validation derives tool identity from each value's
`name`; it still rejects missing, wrong, or extra servers/tools. Provider ErrorNotification and matching JSON-RPC
errors are strictly normalized to closed, secret-free fields. A typed Adapter failure latch/queue owns provider and
inactivity failures; Runner consumes it before startup continuation and before/after notification pumping, records
`runtime/infrastructure,false`, cleans once, and reaches `TERMINAL_REPORT_COMPLETE` without forging a turn terminal.
Only an explicit current-schema progress allowlist refreshes the 300-second inactivity clock; errors, warnings,
startup/status heartbeats, and unknown notifications do not.

This design is deterministic-ready but not live-provider accepted. Independent Round 18 passed all focused and full
regressions and credential scans, while its single empty Luna turn returned a valid active turn and exact Team
Transport surface but no matching completion within the bounded window. start72 remains semantic-PASS evidence but
overall FAIL because the retained evidence contains the historical DeepSeek credential. The user confirmed that key
was revoked on 2026-08-10; the evidence remains unchanged. Independent Round 19 then ran the one permitted
post-revocation empty diagnostic from commit `5a30826`: setup and `turn/start` succeeded, but the Adapter emitted
typed `{stage: inactivity-watchdog, code: llm-inactivity-timeout}` after about 320 seconds without a matching
terminal. No new semantic start is allowed until a Luna smoke produces a matching terminal response.

The user-authorized start72–74 tranche is registered and has two numerical starts remaining. A further three starts,
start75–77, are explicitly authorized but remain a pending strict-ledger extension until start74 is terminal. This
authorization changes only the future budget; it does not waive the security or provider-terminal gates.

## 2026-08-10 explicit formal model binding at thread start

Post-Round-19 diagnosis distinguishes model availability from app-server cold-start resolution. On the current
Codex CLI and host auth, isolated `codex exec` calls completed with exact terminal output for both Luna `medium` and
Luna `max`. By contrast, retained start42 Protocol/Luna artifacts contain two model-catalog refresh failures, two
child-process exit timeouts, and repeated request-send failures; its isolated home contains no model cache. The
current persistent and Examiner app-server paths likewise construct fresh homes and write the frozen model only to
`config.toml`, while their `thread/start` requests omit the `model` field. This matches the upstream app-server cold
catalog failure boundary and explains why a healthy host CLI path is not evidence that the Team path is healthy.

The narrow repair projects the already validated formal manifest model into every formal persistent-role and
Examiner `thread/start` request. The value is exactly `gpt-5.6-luna`; provider and reasoning remain bound by the same
manifest-backed `config.toml`. The Runtime must not read or copy the mutable host `models_cache.json`, infer a model
from ambient config, or accept a second model source. Formal manifest absence, role/package mismatch, or model drift
continues to fail before process launch. Non-formal and R2.3-002 request shapes remain byte-compatible and omit the
new field.

The existing first-turn auth barrier, MCP exact-surface preflight, typed provider/RPC failure handling, inactivity
watchdog, secret audit, and cleanup semantics remain unchanged. Acceptance requires deterministic request-shape
tests for all six formal packages, non-formal compatibility tests, and one independently executed empty-business
app-server smoke from the frozen implementation. The smoke has no business source, platform client, or StartLedger;
only a matching terminal proves the Luna gate. A typed failure or bounded timeout remains Runtime evidence, not a
semantic start or provider PASS.

Round 20 confirmed that the exact Luna model field reached live `thread/start` but the turn still ended in typed
inactivity without a terminal. Its sanitized record omitted notification counts and provider-error projection, so it
cannot distinguish an auth-recovery failure from a silent app-server/provider path. The next bounded step is therefore
one diagnostic-only auth-lifetime differential: preserve the private 0600 auth file until terminal/failure cleanup
while holding every other formal Coordinator input constant. This does not relax the production auth boundary or
authorize a semantic run. A successful terminal would prove the existing unlink point is too early and trigger a new
credential design; another identical inactivity result rejects that hypothesis. The probe retains only safe method
counts/provider categories and destroys/scans the temporary credential at cleanup.

Round 21 failed in the temporary callback before first-turn execution and therefore leaves this hypothesis untested.
Any corrected probe must first pass a no-process callback preflight that proves the single-variable lifetime change,
the existing barrier state/evidence transition, and normal credential cleanup. Only then may one independent bounded
probe run; the blocked invocation remains preserved and is not reclassified.

## 2026-08-10 DeepSeek v4 Flash formal rollback design

The user superseded the Luna provider target after repeated bounded Luna turns produced no matching terminal. The
formal Team now uses one immutable six-package manifest with the exact tuple
`deepseek-v4-flash/deepseek/max`. The Luna manifest is replaced rather than layered, so model/provider/reasoning still
have one source of truth. Shared package declarations, non-formal runs, and R2.3-002 remain unchanged.

The previous DeepSeek process-env path is forbidden because Codex persisted that environment into start72 shell,
session, and SQLite artifacts. Instead, one Runner-owned `DeepSeekProviderProxy` is created for a formal Team run.
Before any formal side effect, credential preflight resolves the fixed repository-external path
`~/.config/ontology-platform/modeling-team-deepseek.env` and requires an owner-owned regular non-symlink `0600` file
with exactly one `DEEPSEEK_API_KEY=<value>` assignment. Prepare retains only an in-memory binding of canonical path,
device, inode, size, and mtime-ns. Runtime start reopens with `O_NOFOLLOW`, requires the same fstat binding, and only
then reads the value, closing the prepare/start TOCTOU window. Neither key nor key digest enters the formal baseline,
manifest, persisted run state, evidence, or child spec.

The proxy binds an ephemeral `127.0.0.1` port and is the only component that receives the real key. Formal persistent
and Examiner TOML points the custom DeepSeek provider at that loopback base URL and deliberately omits `env_key`,
`experimental_bearer_token`, auth commands, and static auth headers. App-server process environments remain the
existing minimal secret-free set; no OpenAI `auth.json` is staged for this provider. The proxy accepts only the exact
Responses API request path/method, rejects oversized or malformed requests, discards any inbound Authorization,
injects `Bearer <key>` upstream, and streams status/body without logging or persisting headers, request/response body,
or provider text. It forwards only a frozen non-auth request-header allowlist, caps request bodies at 32 MiB, disables
ambient proxy configuration and redirects for the fixed TLS-verified `https://api.deepseek.com/responses` upstream,
and applies bounded connect/write/read timeouts compatible with the existing 300-second inactivity watchdog. Evidence
contains only safe counts, bounded status/category, and lifecycle timestamps.

The proxy starts after formal prepare/preflight but before the first Agent process and is shared by all four
persistent roles and both Examiner children. Any proxy startup/death/upstream failure is normalized into the existing
typed Runtime failure queue. Formal DeepSeek keeps the existing first-turn buffer/replay and early ServerRequest typed
response loop, but its credential barrier mode is `provider_proxy`: completing the barrier records one safe
`provider_proxy_ready` transition and requires no `auth_path` or file unlink. The file-backed OpenAI auth transition
remains unchanged for other modes. This avoids both an `auth_path=None` startup failure and reintroduction of the
early-request deadlock.

Shutdown first terminates children and persistent processes, then closes the proxy network listener. While the
mutable key buffer is still available for exact in-memory comparison, the Runtime scans argv/env/config/shell
snapshots/session JSONL/SQLite/WAL/SHM/logs/evidence. Formal DeepSeek audit results persist only scanned-file,
match, matched-secret and matched-surface counts/booleans; they suppress provider-key digests and raw values. After
the final audit the proxy overwrites and releases its key buffer. A credential file is Host configuration and is never
copied into a run root.

Formal persistent and Examiner processes also receive one lifecycle-owned bounded stderr drain. It continuously
consumes the pipe so provider diagnostics cannot deadlock the child, compares bytes against the provider sentinel with
an overlap window large enough to detect a value split across chunks, and retains only byte/chunk/match counts. It
never writes or returns stderr content or a provider-key digest. A match feeds the same credential-cleanup failure;
drain startup/join failure is a typed Runtime failure. Non-formal stderr behavior is unchanged.

Acceptance requires fake-upstream streaming and header-injection tests, path/method/body-limit rejection, six-package
formal projection, non-formal compatibility, process/child lifecycle and exactly-once cleanup, secret-bearing negative
tests across every artifact class, full regression, service restart/health, and one independently executed empty
Coordinator smoke. That smoke has no business source, platform client, Runner reservation, StartLedger, Examiner, or
semantic modeling. Only a matching turn terminal plus zero secret/residue passes the provider gate.

Independent Round 25 accepted this design at Runtime/provider scope. The repaired formal config parsed with one exact
model tuple, the live empty Coordinator turn completed through the loopback proxy, upstream returned 2xx, and all
credential, stderr, artifact, child and proxy cleanup checks were zero-residue. This opens the existing start73
authorization only; semantic modeling and Acceptance remain unexecuted under this rollback.
