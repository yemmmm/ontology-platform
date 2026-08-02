# R2.3-002 New-Scope Business Slice Design

## Status and sources

- Status: Round 52 plan revision; ready for plan re-review (no implementation handoff)
- Requirement: `docs/requirements/requirements-v2.3.md`, R2.3-002
- Base: R2.3-001 Team Runner at `f441682`
- Reused scenario: `docs/evaluation-scenarios/ontology-modeling-team-l3/`
- Delivery record:
  `docs/delivery/records/2026-07-31-r2-3-002-new-scope-business-slice-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-31-r2-3-002-new-scope-business-slice-test-plan.md`

## Goal

Use the accepted R2.3-001 foreground Team Runner and base three-Agent Profile to complete one
fresh, bounded Dify Workflow-as-Tool `C -> B -> A` modeling loop through the formal platform MCP.
The successful non-empty Project/Ontology is retained with a minimal immutable handoff for
R2.3-003. The change proves modeling and retrieval quality on one accepted slice; it does not add a
product scheduler, scenario launcher, Judge, Consumer, or platform-specific Dify behavior.

## Current minimal scope

The implementation extends only the repository-local `modeling_team/` configuration and lifecycle
surfaces needed for a real Task:

- Task schema v2 declares per-role source sets, the exact Protocol MCP tool allowlist, semantic-start
  evidence, and whether a successful non-empty create scope is retained;
- Runner stages role-private sources without flattening paths, records a manifest and all
  runtime-affecting hashes, and builds the first-turn text from the Task instead of hard-coding the
  R2.3-001 health smoke;
- Codex Adapter exposes exactly the Task-declared formal platform tools to Protocol and verifies
  that exact MCP surface before the first turn; other roles still receive no platform MCP;
- PlatformScope distinguishes empty failure cleanup from successful non-empty retention, captures
  final workspace context, closes failed Build Sessions when safe, and revokes credentials;
- a small repository-local, append-only, lock-protected execution ledger enforces the initial
  two-start budget plus explicit deduplicated user-authorized extensions across distinct run IDs,
  and records each failure classification and tested repair baseline;
- Team Transport enforces Coordinator-last terminal ordering, rejecting a premature Coordinator
  terminal result until Modeling and Protocol have each reported completed or blocked while leaving
  the Coordinator Runtime available to finish in-flight user and teammate communication. A rejected
  call is not a recorded result and does not consume the exactly-once-success rule; the error names
  the missing roles, and the Coordinator-visible Package/Task contract requires retry after their
  terminal handoffs. The dependency comes from Profile roles and applies to both v1 and v2 Tasks;
- Team Transport also enforces Modeling-before-Protocol terminal ordering. Protocol sends each
  receipt or translation conflict while it is still active. Modeling either sends a revised
  platform-neutral candidate and awaits another Protocol response, or reports completed/blocked.
  Runner then delivers Modeling's immutable terminal result to Protocol; Protocol may report only
  after that handoff, and Coordinator remains last. Dependency rejections do not count as a
  successful terminal result;
- after independent semantic PASS, a deterministic publisher verifies the retained producer state
  again and emits the five-field scope handoff;
- one committed R2.3-002 Task references the already frozen L3 Agent-visible sources. The three
  tester-only answers remain outside every role source set and are released only as verbatim outer
  user messages after a grounded Coordinator question.

Task schema v1 remains valid and retains the R2.3-001 prohibition and health-only behavior. No
backend or frontend change is planned.

For every v2 role, first-turn text enumerates the exact absolute staged paths that role must read
before requesting work or reporting terminal. Protocol's enumerated sources include the public
`modeling-batch-item-contract.json`; that file is the platform-generic construction contract to use
when the Runtime-rendered MCP signature collapses nested Items to `Array<unknown>`, not a tester
answer or a conflict with the registered tool. Modeling sends a semantic candidate expressed as
classes, properties, relations, Shapes, instances, evidence, and explicit unknowns. Protocol alone
maps that meaning to Batch/Item envelopes and must not delegate platform payload authorship back to
Modeling.

Attempt eleven exposed a create-only ordering invariant missing from that construction contract.
Protocol now treats the candidate's dependency graph as immutable semantic input and performs only
a platform-mechanical topological schedule across Batches: classes; properties and relation types;
entities; a receipt/read boundary that binds generated entity IRIs; relations; then Shapes whose
target instances and required property/relation paths already exist. Every stage uses its own
dry-run and apply request and advances the workspace version only from the formal receipt. This is
not semantic `item_reordering`: Protocol may not change meaning or dependencies inside the
candidate. If a dependency cannot be bound, it returns a conflict before applying the dangerous
Shape. It never relies on deleting/deactivating an applied Shape or weakening SHACL validation.

Before another Producer start, one no-model production-path preflight uses the real Protocol
Adapter, bwrap, app-server, and native MCP RPC in a fresh temporary scope. It applies a minimal
platform-generic class/vocabulary/entity/relation/relationship-dependent-Shape sequence, observes
successful validation, and then proves zero Session/Lease/key/Project residue. It does not receive
business sources, write the semantic-start ledger, or touch retained attempt evidence.

Attempt twelve exposed one adjacent generated-tool schema loss: the MCP surface renders
`validation_scope` as an unconstrained string although the service accepts only `asserted_only` and
`asserted_plus_reasoning`. The same Protocol-private platform-generic reference therefore records
those exact values and their mechanical selection rule. The normal separated validation/reasoning
flow sends explicit `asserted_only`; `asserted_plus_reasoning` is permitted only when the intended
validation includes a formally receipted reasoning result graph and its graph IRI is bound. Any
other value or missing required graph binding fails before the call. A no-model native-MCP preflight
must observe `asserted_only` success and `all` rejection, then prove zero residue before another
Producer baseline is authorized.

The first completed retained Producer exposed an internal shape mismatch at cleanup: the scope
cleanup result intentionally includes `mode`, terminal Session evidence, and key-revocation status,
while the offline-handoff writer rejected every key beyond its seven formal inputs. The writer must
accept this trusted internal cleanup superset, validate that all seven formal fields are present and
valid, and additionally require `mode=create`, `sessions_terminal=true`,
`protocol_key_revoked=true`, and `admin_key_revoked=true`. A missing or false safety confirmation
remains fatal. It then
projects only the formal handoff fields into the immutable retained-handoff input. Extra cleanup
metadata is never serialized; missing/invalid formal fields and overwrite attempts remain fatal.
Recovery reuses the already completed Session and retained Project and must not rerun semantic work.

## Functional contract

### Role inputs and startup

The new Task uses schema v2. Every source entry has a stable repository-relative path, an input
classification, and one or more allowed roles. Runner copies it under the same relative path inside
each allowed Agent's private `/agent/home/sources/` tree and writes a SHA-256 manifest before Agent
startup. A source may not target `tester-only`, runtime evidence, delivery documents, or historical
run paths. Duplicate staged paths, missing files, symlinks, path escapes, unknown roles, unknown
tools, and secrets fail before scope or Agent startup.

The R2.3-002 Task supplies Modeling with the L3 business sources and questions, Protocol with the
public platform protocol, and Coordinator with only the coordination task plus business sources
needed to ask grounded questions. Every role receives the common objective and roster. The existing
bubblewrap, no-host-repository, fresh Thread, Skill, Package, transport, and secret boundaries stay
unchanged.

### Formal platform tool surface

Protocol receives only the exact v2 Task allowlist:

- platform health and context reads;
- Build Session create/read/complete/cancel;
- Ontology Lease acquire/renew/release;
- Modeling Batch submit/read/list and ontology read model;
- semantic validation, reasoning, governed context query, lineage, and statement provenance.

The allowlist is validated against a repository-owned constant and cannot include API-key,
Project/Ontology lifecycle, migration, repair, governance-write, or generic semantic-edit tools.
Runner owns only Project/Ontology/key mechanics. Modeling owns semantic content; Protocol owns
canonical platform arguments and calls. Runner never constructs Modeling Items, queries, or
semantic answers.

### Collaboration and user continuation

Coordinator assigns Modeling and Protocol through Team Transport. Modeling sends Protocol
business/ontology candidates directly; Protocol returns receipts or semantic conflicts directly.
Coordinator remains the sole outer question channel. The delivery controller matches a pending
plain-business question to one frozen tester-only answer and sends that answer verbatim using the
existing Runner outer-user action. Answer matching is delivery/test mechanics, not Runner,
Profile, Package, Skill, or Agent input.

The foreground newline-delimited control envelope is exact: a user answer is canonical JSON with
`action="user"` and the verbatim `text`; stdin decoding passes that object to
`TeamRunner.receive_outer`, which emits one `RuntimeDelivery(kind="outer-user")` to Coordinator.
The delivery procedure generates this object deterministically and preflights the stdin-to-adapter
path without a model turn before any repaired producer start. Undefined `type=user_message` or any
other action is rejected and is never used as a substitute.

Envelope validity does not authorize an answer. During the producer, Delivery waits until the
current run exposes a grounded Modeling question and Coordinator prompt, freezes its delivery ID
and exact text, maps it to one unique tester-side answer ID, and confirms the run has not already
recorded that or any unasked answer. It then writes the pre-encoded JSONL exactly once. Direct
evidence must connect question, one outer-user record, and Coordinator's correlated forward to
Modeling. Repeated prompts are observations of the same pending question and never release another
answer.

The same run and fresh Sessions continue until all three Agents report terminal results and settle.
The Runner records direct deliveries, outer questions/answers, tool events, terminal results, and
the post-settlement Coordinator summary without interpreting their semantics.

### Semantic start and immutable baseline

Preparation and role visibility probes occur before Modeling receives the real business task. The
delivery procedure records the timestamp at which the frozen Task is first delivered to Modeling;
that is the semantic start. Before it, Runner records hashes for Runner, Adapter, Profile, Packages,
Skills, Task, every source, and relevant platform MCP code. After it, runtime-affecting changes
terminate and preserve the attempt.

An ignored repository-local execution ledger is the single authorization source across all
R2.3-002 run IDs. It is append-only and protected by an advisory file lock. Before Project/key
creation, Runtime startup, or delivery of real business input, the Runner atomically reserves a
run slot and binds run ID, baseline manifest hash, reservation timestamp, and state. Reservation
one must satisfy the 20-minute gate measured from the reviewed implementation-ready freeze.
Every reservation after the first is accepted only when the immediately preceding counted start has
a frozen terminal record classified `runtime/infrastructure`, `platform-contract`, or
`collaboration/routing`, explicitly states that no complete modeling-quality result was produced,
and binds a tested repair plus a new baseline hash. The initial cap is two. An append-only,
deduplicated user-authorization record may raise that cap by an exact positive number. The first
2026-07-31 authorization raises it by two to four total starts; after attempts three and four ended
in retryable collaboration failures without complete applied/validated results, a second explicit
authorization raises it by two to six total starts. After attempts five and six both exposed the
same isolated-Protocol-MCP `legacy_only` platform-contract failure without a complete modeling
quality result, a third explicit authorization raises the cap by two to eight total starts. Attempts
seven and eight then exposed distinct pre-write Protocol mechanics/Build Session platform-contract
failures without a complete modeling-quality result; independent Round 21 proved the narrow repair.
The user's fourth explicit authorization raises the cap by two to ten total starts. On 2026-08-01
the user replaced the per-exhaustion approval contract with one continuing authorization through
R2.3-002 completion. The Delivery Agent may therefore append further exact `+2` authorization
tranches without another user interaction. Each tranche has a unique ID and reference that bind
the continuing authorization plus its sequence; the ledger never records an infinite cap and every
semantic start remains counted. Completion, explicit withdrawal, or requirement termination ends
that authority. Concurrent, over-budget, duplicate,
unclassified, modeling-quality, or drifted reservations fail before scope or Runtime creation. A
pre-semantic configuration reservation can be released with an append-only correction; a recorded
semantic start can never be uncounted. Repeated cleanup is idempotent and preserves the first
release record. Release is a terminal reservation state: `mark_semantic_start` rejects any run with
an existing release, and the file lock makes release-versus-start races choose exactly one winner.
If a run-ID-bound repair baseline was consumed only by a reservation that then
failed and released before semantic start, the controlled repair CLI may append a new binding for
the original failed semantic run. It accepts this rebind only when the prior repair was used by
exactly one released, never-started reservation and the new nonempty baseline differs; unused,
active, semantically started, misordered, or concurrent rebinds fail closed. The next run still uses
a fresh ID and the ordinary exact-baseline and 20-minute reservation checks.

The minimal ledger change removes only the historical four-authorization ceiling. It retains exact
`+2` increments, append-only deduplication, single active reservation, retryable previous-failure,
`complete_modeling_quality_result=false`, independently tested repair, exact new baseline, and
freeze-time gates. Delivery appends at most one tranche when the current cap is exhausted; it does
not preallocate an arbitrary future budget or let the Runner authorize itself. `authorize_budget`
performs the exhausted-cap check under the same ledger lock: semantic-start count must equal the
current replayed cap. Once one tranche is appended, a second synchronous or concurrent request
sees a higher unconsumed cap and fails. Cap validation replays records in order and rejects an
authorization that appears before the previous cap was fully consumed, even when its amount, ID,
and reference are otherwise well formed. The historical sequence remains valid because its four
tranches follow semantic-start counts 2, 4, 6, and 8.

The Codex CLI checks the host authentication artifact before reservation, run-directory creation,
or PlatformScope preparation. A missing/non-file `CODEX_HOME/auth.json` is a deterministic
runtime/infrastructure preflight failure. Runtime staging repeats the check defensively; it never
falls back to another agent's credentials or hidden outer-session authentication.

The canonical-mode preflight is process-local, not service-local. Codex Adapter owns one fixed
three-entry Protocol-MCP environment contract:
`SEMANTIC_CANONICAL_STORE=rdf`, `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`, and
`SEMANTIC_READ_MODE=canonical`. Adapter renders those exact values only into the private
`mcp_servers.ontology_platform.env` block; it does not read, copy, or hash the outer
`os.environ`, does not depend on systemd-manager inheritance, and does not expose the values to
Coordinator or Modeling MCP configuration. Baseline manifest contains the canonicalized three-entry
contract as a dedicated runtime value, so any name/value drift changes the baseline hash. One
production helper constructs the Protocol MCP command, cwd, non-secret mode map, secret/project
connection entries, and enabled-tool surface; private config rendering and preflight both consume
that helper rather than duplicating a dict.

The independent preflight creates a fresh temporary PlatformScope and Protocol key and stages one
Protocol roster member through the production Codex Adapter. On that same Adapter/config/scope it
separately proves: the real bwrap namespace exposes the exact read-only mechanics mount; the
production dynamic-read callback returns canonical current-run bytes and rejects every drift case;
and the real app-server's native MCP RPC reaches the configured ontology-platform child for health,
Session/Lease, and one `create_class` dry-run. It must observe `validated`, then
release/cancel/delete/revoke and prove zero residual state. This is deliberately deterministic and
does not require the model to choose `exec` while its normal Protocol instructions tell it to wait
for a Modeling candidate. Callback evidence is labeled as callback evidence, not model behavior.
No business sources are delivered and no semantic-start ledger event is created. Tests also inspect
the produced Coordinator and Modeling configs and require that none of the three canonical-mode
entries is present. A standalone subprocess that merely receives the same map, or checking only the
regular systemd service, is insufficient.

Attempt ten proved the same process-local rule also applies to semantic reasoning: the isolated
ontology-platform MCP does not inherit `backend/.env`, so the host's configured development
reasoner is absent inside that child. The narrow repair extends the production Protocol MCP launch
spec with the fixed non-secret value
`SEMANTIC_REASONER_COMMAND=/backend/scripts/dev_owl_reasoner.py` and the deterministic child-only
`PATH=/backend/.venv/bin:/usr/bin:/bin`. The latter is required because the script uses
`#!/usr/bin/env python3`; it resolves the already mounted backend venv interpreter that contains
`rdflib`, rather than the system Python which does not. Only a schema-v2 Protocol
namespace receives an exact read-only bind of the accepted
`backend/scripts/dev_owl_reasoner.py` host file at that path; no scripts directory, repository,
`.env`, or ambient environment is mounted or copied. Coordinator, Modeling, schema-v1, and the
Codex app-server's general environment receive neither the reasoner command nor this fixed PATH.
The baseline records the reasoner command, the exact PATH contract, and the script SHA-256 so path,
environment, interpreter resolution, or implementation drift creates a new baseline.

Before another producer authorization, an independent no-model preflight must reuse one temporary
scope, Protocol key, production `CodexRuntimeAdapter`, rendered private config, bwrap namespace,
real app-server, and native MCP RPC path. It first proves exact mount/config isolation, then applies
only the minimum temporary semantic input needed to invoke `run_semantic_reasoning`, and directly
requires a succeeded run with `consistent=true`. It verifies the configured namespace path and
host script digest, cleans Session/Lease/Batch/Project/Ontology/key/runtime state to zero, leaves the
live start ledger unchanged, and does not read or mutate attempt ten's retained evidence. The
development reasoner is the same conservative RDFS implementation accepted by the reused L3
scenario; this repair restores the frozen R2.3-002 reasoning gate and does not claim full OWL-DL
coverage or promote that development command into a production architecture decision.

Attempt eight exposed a second platform-contract mismatch before Session creation. Protocol placed
the Runner `run_id` and custom phase/workspace fields inside `initial_checkpoint`; authorization
recursively interpreted that `run_id` as an owned platform resource and rejected it, while the same
object also violated the formal `InitialBuildCheckpoint` schema. The narrow repair does not change
backend authorization. Only the v2 new-scope Protocol tool surface gains `save_build_checkpoint`.
The mechanics contract requires `create_build_session` with `initial_checkpoint` omitted or null,
then an initial checkpoint `<run_id>-initial` using the create receipt revision, `phase=modeling`,
`current_step=schema_and_instance_modeling`, `next_step=validation_and_reasoning`, the scoped
ontology ID, and no custom fields. Lease acquisition uses the revision returned by that checkpoint.

After dry-run/application, validation, reasoning, and governed queries, Protocol must reread the
Build Session and save a second checkpoint `<run_id>-final` using exactly that Session receipt
revision, `phase=handoff`,
`current_step=semantic_acceptance_complete`, `next_step=delivery_handoff`, and the scoped ontology
ID. Completion uses the final-checkpoint receipt revision and is followed by Session reread, as the
frozen public protocol requires. Before any further producer authorization, one deterministic
Protocol-only production preflight first proves the former nested-run-ID create is rejected with
zero Session, then uses a fresh client session to exercise create(null), both checkpoint revisions,
lease acquisition, a validated minimal dry-run, and full release/cancel/delete/revoke cleanup with
zero residual state. It starts no model and writes no semantic-start ledger event.

Attempt seven exposed one further frozen-input mismatch before any platform write:
`public-protocol.md` requires `/opt/mechanics-contract.json`, while the standardized namespace did
not mount it. The narrow repair reuses the semantic-free R2.2 L3 mechanics-contract content. The
Adapter generates it in a run-owned host staging directory that has no writable namespace alias,
then gives only Protocol an exact read-only bind at `/opt/mechanics-contract.json`. It is never
placed under the writable private Agent home; Coordinator, Modeling, and v1 runs neither generate
nor mount it. The baseline hashes the helper implementation and already binds the run ID. Tests
prove in-namespace readability, failed chmod/write, absent aliases, unchanged host hash, and no
business facts, tester-only answers, or secrets before the final start is authorized.

The Adapter also mediates model-issued `cat` through a host callback rather than executing that
command directly inside bwrap. Consequently, the callback exposes exactly the one virtual mechanics
path only to the registered v2 Protocol instance. It binds raw and resolved paths to the current
run-owned asset, rejects symlinks, non-regular files and non-`0444` mode, reads through a no-follow
file descriptor, and compares those same bytes with the canonical run-ID-bound SHA-256 before
returning content. This validation and read are one operation; no general `/opt` root is added to
the existing Skill/source allowlist.

Latest-Version resolution is a frozen semantic gap. Modeling may describe the published versions and
the workflow-identity configuration from source, but it may not assert B's concrete resolved C
version until it has asked Coordinator the grounded Tool-binding question and received the released
outer-user answer. Candidate instructions and independent tests reject the prior inference from
`published_latest` plus absence of a separate B deployment; without an answer the value remains an
explicit unknown.

Coordinator terminal ordering is enforced end to end rather than only inside the Broker. A
premature `report_task_result` receives a structured dependency error and leaves the Agent Session
active. The only professional terminal order is Modeling, then Protocol, then Coordinator;
completed versus blocked does not change that order. Runner delivers Modeling's immutable terminal
handoff to Protocol and Coordinator, then Protocol's handoff to Coordinator. Coordinator retries
`report_task_result` only after both, which is its single successful registration, and normal 3/3
settlement continues. Tests cover each dependency rejection, ordered handoff, retry, settled
emission, and cleanup eligibility for both Task schema versions.

Professional conflict loops use the same end-to-end dependency delivery. Protocol cannot register
terminal before Modeling. A Protocol-to-Modeling receipt/conflict is delivered while both remain
active. Modeling instructions require it to wait for that response before terminal; on a conflict it
either revises and waits again or reports blocked. Runner forwards Modeling's terminal result to
Protocol, waking the Protocol Thread to make its single successful terminal report. Runner then
forwards both professional results to Coordinator. Tests cover successful receipts, a revisable
conflict with a second candidate, an unrevisable conflict, premature Protocol rejection, dependency
handoff, 3/3 settlement, and cleanup without introducing typed semantic message schemas.

Delivery gates use explicit transport acknowledgements, not queue state. `send_team_message` adds
optional `expects_reply` and `reply_to_delivery_id` metadata, while Runtime delivery envelopes expose
the immutable `delivery_id`. Modeling marks a candidate/revision that requires Protocol feedback;
Protocol's response names that exact delivery. Ordinary one-way messages do not open a gate, and an
unrelated reverse message cannot close one. Runner calls the Broker acknowledgement only after
`adapter.send_message()` returns successfully; for this local Adapter contract, that return means
the Runtime accepted the turn/steer input, which is the delivery boundary. A matching reply closes
its request only after that reply is likewise accepted by the Modeling Runtime.

Terminal dependency release uses the same boundary. Recording Modeling's result in the Broker does
not let Protocol terminate. Runner first injects the immutable Modeling terminal handoff into the
Protocol Runtime and then acknowledges that handoff to the Broker; only then can Protocol register.
The same rule applies to both professional handoffs required by Coordinator. Interleaving tests
prove that `reply queued -> Modeling report before drain` and `Modeling result recorded -> Protocol
report before terminal-handoff delivery` are both rejected, while each succeeds after the relevant
Adapter acceptance.

Delivery IDs are unique across one run. A `reply_to_delivery_id` must name exactly one still-pending
direction-reversed `expects_reply` delivery and can close it only once. Modeling that has never
opened such a request may report blocked for a pre-candidate failure, but may not report completed
without a delivered Protocol response.

### Scope terminal behavior

Protocol must finish all Attempts, complete the successful Build Session, and release its Lease.
After Runtime settlement or failure, PlatformScope uses the ephemeral admin principal to read the
authoritative Build Context, every owned Build Session and Modeling Batch Attempt, Lease state, and
workspace revision before any destructive action. On failure it:

1. stops with a cleanup blocker if any Attempt is `applying` or `recovering`, identity/ownership is
   ambiguous, or workspace identity drifted;
2. idempotently cancels each owned non-terminal Build Session through the formal HTTP API, which
   releases its Leases, then re-reads the Session/Lease/Attempt state;
3. refuses to use Lease expiry as completion evidence;
4. only after terminal state is proven, applies the scope disposition below.

PlatformScope then revokes the Project model key, reads current workspace context, and:

- deletes the exactly owned Project when the create scope is still empty;
- retains an exactly owned non-empty Project only when Task policy is `retain_nonempty`;
- otherwise refuses deletion and reports a cleanup blocker.

Successful producer retention is not an error. Cleanup records
`scope_disposition=retained-pending-acceptance`, final workspace version, completed Build Session
identity, absence of in-flight Attempts/active Leases, key revocations, stopped Runtime identities,
and destroyed secrets. A failed written scope records `failed-written-retained`; it never becomes a
handoff candidate.

Failed written scopes are never auto-deleted by Runner. After evidence freeze, delivery/test cleanup
may delete only an exactly owned failed Project and must retain the direct receipt.

### Handoff publication gate

Runner cleanup does not publish the R2.3-003 handoff. Independent acceptance is one fresh
read-only Agent flow with two explicit phases. In Phase A, after the producer team settled, direct
platform terminal checks passed, and evidence froze, the Agent evaluates every semantic,
collaboration, isolation, Batch, query, and lifecycle gate except the not-yet-published handoff. It
must return `PHASE_A_PASS`, `FAIL`, or `INCONCLUSIVE`; `PHASE_A_PASS` is an intermediate semantic
and producer-terminal verdict, not the requirement's final PASS.

Only after `PHASE_A_PASS`, the main Delivery Agent invokes a deterministic handoff publisher. The
publisher:

- accepts only a `retained-pending-acceptance` producer record whose three Agent results are
  completed and whose independent Phase A verdict is PASS;
- uses a new short-lived read-only/admin bootstrap solely to re-read Project/Ontology ownership,
  completed Build Session, absence of in-flight Attempts/active Leases, and exact final workspace
  version, then revokes it;
- rejects failed, incomplete, drifted, already deleted, or already published scopes;
- atomically creates exactly one immutable JSON document with run ID, Project ID, Ontology ID,
  final workspace version, and `scope_disposition=retained`.

The independent Agent never receives the publishing credential and cannot invoke the publisher.
After publication, the Delivery Agent resumes the same independent acceptance Session with only
the immutable handoff path plus direct read-only platform evidence. In Phase B, the Agent verifies
the exact five fields, producer identity/version binding, immutability, and absence of secret or
semantic duplication, then returns the final requirement PASS/FAIL/INCONCLUSIVE. Phase B cannot
reopen or mutate the producer run. Existing-mode drift enforcement and final retained-scope
deletion remain R2.3-003 work.

### Independent acceptance

After producer settlement and evidence freeze, a fresh no-history, read-only acceptance Agent
receives the frozen requirement, tester-only acceptance contract, exact baseline, raw events,
platform receipts, query outputs, and cleanup evidence. It may perform supplementary read-only
platform queries. Phase A reports every non-handoff gate with direct citations. Only after Phase A
PASS and external handoff publication does the same Session receive the handoff for Phase B and
return the final PASS, FAIL, or INCONCLUSIVE. It cannot create, resume, steer, or mutate the
producer run.

### Attempt-fourteen semantic and retrieval repair

Attempt thirteen's independent Phase A found that the team stopped its grounded-question loop after
the first answer: a second consumer-critical source ambiguity was therefore modeled as unknown even
though the user-held answer could have resolved it. The Modeling contract must perform a generic
material-gap closure loop before freezing a candidate: derive gaps only from its visible sources and
consumer questions, ask one grounded question at a time, incorporate the answer, then reassess the
remaining material gaps. It must not know the tester answer set, answer count, or expected ontology.
An explicit unknown is valid only when visible evidence or a received answer leaves the fact
unresolved; the first answered question never implicitly closes later gaps.

The Protocol retrieval contract also becomes fail-closed. Before returning a successful receipt it
must demonstrate an ontology-scoped generic query with no silent truncation, no missing required
Evidence/lineage, no cross-ontology facts, and a mechanically valid continuation whenever paging is
required. A degraded vector path is not itself fatal if a generic scoped fallback returns complete
evidence, but an invalid cursor or incomplete result is a concrete blocker. Modeling must reject a
Protocol receipt that declares those conditions instead of reporting completed. This remains a
platform-generic completion gate and does not encode C, B, A, field names, or tester answers.

Fallback completeness is mechanical, not inferred from an empty warning list. The verifier accepts
the full `{ok,data}` MCP envelopes Protocol actually obtains. Every input must have `ok is true` and
an object-valued `data`; it parses only `data.*` and never falls back to similarly named root fields.
The proof contains initial and final
`get_modeling_context`, `get_ontology_workspace_context`, an exhaustive
`list_session_modeling_batches` inventory, one `get_modeling_batch` detail per inventory Batch, and ontology-
scoped entity/fact reads. It binds the selected identity from `modeling_context.ontology.id` and the
workspace's exact asserted-ontology, asserted-data and Shapes members/owners. The initial context
must have zero authoritative counts. Each Batch detail must bind the target `ontology_id`, immutable
content hash and command-bearing Items/resource outputs. A write Batch has exactly one formal
applied `apply_atomic` Attempt; only that Attempt's normalized delta, delta hash and nested workspace
before/after versions contribute to the reconstructed write set and contiguous workspace chain. A
non-write Batch contains only `dry_run` Attempts with `validated` or `validation_failed` status and
must contain no applied, partially-applied, applying, recovering or other write-state Attempt; its
proposed delta is deliberately excluded from the applied model.

The inventory is taken unfiltered after the Session and all writes are stable, uses a declared
request limit greater than the returned Batch count, and requires no next cursor; its exact Batch-ID
set equals the supplied details, so rejected validation probes are retained while no write is omitted. Create
class/property/relation-type deltas may insert only into the bound asserted-ontology graph;
entity/relation deltas only into asserted-data; Shape deltas only into the exact bound Shapes graph.
Deletes, clears, drops, unknown graphs and command/graph mismatches block. Resource-output counts for
class/property/relation-type/Shape/entity equal final authoritative counts. Relation identity comes
from the formal Item payload and its exact data-graph triple. With statement-list's platform hard
maximum, effective facts-read capacity is `min(requested_limit, 1000)` and must be strictly greater
than the expected statement count; an expected count at or above 1000 blocks this fallback. The verifier reconstructs canonical
object terms on both sides and computes platform four-term fact IDs from normalized asserted-data
inserts and raw statement-list fields `subject`, `predicate`, `object`, `object_kind`, optional
`object_datatype`/`object_language`, and `source_graph_iri`. The two computed ID sets must be exactly
equal and every fact row binds the asserted-data graph. Its distinct `subject` count equals the
authoritative fact count, and relation source count equals the authoritative relation count. Raw
entity-list `iri`s equal formal entity resource-output IRIs and each `source_graph_iri` is the bound
data graph. If a read response omits
completeness metadata, that omission provides no
proof by itself: fallback may compensate only with exact authoritative-count equality and a known
response capacity sufficient for that count. If capacity is below or unknown, or any receipt chain,
count, output identity, or ownership cannot be proved, fallback blocks. Modeling's candidate
identifies its required assertions as exact current asserted-data quads; verifier computes each
statement/fact ID. Schema and Shapes statements are not required-assertion inputs. Each requires the
raw full envelope from `get_ontology_lineage(target_type=statement,
target_id=<fact_id>)`: top-level data binds the same Ontology and exact target, is non-truncated, and
contains a matching item with the same statement ID/quad, technical-trace Graph Set/data graph,
origins, and supporting-context Evidence references. The deprecated resource-level provenance tool
is not a completion gate. Missing exact lineage returns a concrete blocker. Generic query cursor
continuation is outside this fresh-create read-model fallback because its proof contains no generic
query receipt; Batch inventory retains its real `next_cursor` gate. Round 32 exercises this exact
algorithm through the production Adapter and native MCP
against a temporary non-semantic scope, including degraded-vector success, multiple relation triples
sharing one source, and receipt-count, wrong-ontology receipt, missing/drifted relation triple,
provenance, read-count/ownership, missing and extra same-subject fact triples, and Batch-inventory
paging negative cases, followed by exact cleanup.

The deterministic verifier is delivered as a Protocol-private local MCP server, not an import from
the hidden host repository and not a Semantic Platform API. Runner copies the verifier module and a
minimal stdio MCP wrapper into the run's immutable runtime assets, verifies their exact regular-file
identity/digests against the frozen baseline, holds verified descriptors open, passes those
descriptors into bwrap, and read-only mounts `/proc/self/fd/<n>` rather than re-resolving replaceable
paths. Only those stable inodes appear under `/opt` in the Protocol namespace. The
Protocol Codex configuration starts that required local server with `/usr/bin/python3`; Coordinator
and Modeling receive neither the files, mount, configuration nor tool. The wrapper exposes only
`verify_scoped_retrieval_fallback(proof)` and returns a structured pass or fail-closed error. It has
no platform credential, network client, filesystem mutation, semantic query authoring, or business
logic. The wrapper, verifier, Agent-visible server/tool/launch contract and Adapter launch code all
enter the repair baseline. The reference and Protocol instructions name the exact
`protocol_mechanics.verify_scoped_retrieval_fallback` native MCP call; a host Python import is not a
valid path. Before the first turn and before semantic start, schema-v2 MCP preflight requires exactly
`team_transport`, `ontology_platform`, and the one-tool `protocol_mechanics` server for Protocol,
and exactly `team_transport` for the other roles. Missing, zero-tool, wrong-tool, extra-tool, extra-
server, or wrong-role surfaces fail and release a pre-semantic reservation. Existing mechanics-
contract and reasoner mounts remain file-scoped and unchanged in meaning.

## Failure classification

### Round 32 B32-03 statement-list scope repair

The second real-response retry proved that `statement-list` receives the correct Ontology Graph Set
and asserted-data graph from the scope resolver but its SPARQL template leaves `?graph` unbound.
`RdfStoreRepository.query_read_model` records `graph_iris` only as a diagnostic comment, so the
query scans every live named graph and bounded results can omit the requested Ontology entirely.
The minimal generic repair first selects only members whose exact role is `asserted_data` for the
`statement-list` path, then binds `?graph` with that role-filtered `{graph_iris}` VALUES list inside
the template. The ordinary source list cannot be reused because it also contains
`asserted_ontology`. No other read model's graph selection changes. The repair does not change the
route, response schema, repository, limit, verifier, or any business concept. A regression must
prove the compiled query is restricted to the requested current asserted-data graph and excludes
both the same Graph Set's asserted-ontology statements and a second Ontology's data statements.
Round 32 then repeats the production Protocol native-MCP positive, proof-copy negative matrix,
cleanup and frozen-ledger checks before Attempt 14.

### Round 32 B32-04 computed fact-ID repair

The scoped facts response intentionally exposes the raw statement fields, not a `fact_id`. The
verifier already reconstructs the canonical object term and computes the platform four-term fact ID
from those fields, but then incorrectly requires the absent response field to equal its computed
value. Remove only that synthetic-field requirement. Read-model rows and candidate exact quads are
identified by the computed ID; the proof's lineage-request record still carries the computed
`fact_id` so its raw `get_ontology_lineage(target_type=statement,target_id=...)` response can be
correlated and checked. No platform response field is added and no caller-supplied ID can override
the computation. Unit tests must accept an unmodified row with no `fact_id` and reject a proof whose
computed quad differs from applied deltas or lineage.

### Round 32 B32-05 read-envelope scope binding repair

Generic entity-list and statement-list envelopes expose `graph_set_id`, `source_signature`,
`model_name`, `include`, warnings and items; they do not expose `ontology_id`, `truncated` or
`next_cursor`. The verifier must bind both reads to the already verified workspace's exact
`default_graph_set_id` and final `source_signature`, require the matching model name and asserted
include, and require every row's `source_graph_iri` to be the bound asserted-data graph. Entity IRIs
still exactly equal formal entity outputs and their count equals final context. Statement IDs remain
computed from raw rows and exactly equal the applied asserted-data delta set. Because statement-list
has no cursor/completeness fields, completeness remains proven only when effective capacity is
strictly greater than the expected applied statement count and exact set/count equality holds; no
missing response field is invented. This replaces all remaining synthetic identity/paging checks in
these two reads without weakening workspace, graph, identity, count or capacity gates.
Protocol captures the workspace receipt only after the final write and Session state are stable;
entity/fact reads follow without an intervening source-graph mutation, so the final Graph Set ID and
source signature remain authoritative across both reads.

### Attempt 14 B32-06 mandatory eligible fallback routing

Attempt 14 proved the model and platform writes but Protocol treated the deterministic fallback as
optional: after the governed query reported truncation, degraded vector recall and missing
Evidence/lineage warnings, it returned a conflict without calling the preflighted native verifier.
For a fresh-create run whose generic query is incomplete and whose formal fallback inputs are
available, Protocol must collect those unmodified receipts and call
`protocol_mechanics.verify_scoped_retrieval_fallback` before terminally blocking. A complete verifier
result is the governed retrieval-completeness receipt despite the degraded vector path; an
incomplete proof or tool error remains a concrete conflict. This changes routing priority only, not
the verifier, platform API, semantic candidate or evidence requirements. A Protocol-only production
preflight must prove the Agent actually calls the native tool after an incomplete query and reports
success only from `complete=true` before another semantic start.
Attempt14 first receives one immutable `collaboration/routing` terminal-failure record with
`complete_modeling_quality_result=false`: it settled blocked before an accepted retrieval receipt or
completed Session, and ordinary scope cleanup is not a ledger terminal. After the independent
preflight passes, the new baseline is bound to that failure by repair authorization before the fresh
reservation; ledger replay must prove the reservation is accepted.

### B32-07 Protocol verifier elicitation authorization

The Protocol-only preflight proved that exact server/tool startup is insufficient: App Server sends
an elicitation request before the Agent's native MCP call, and Adapter's older allowlist declined
`protocol_mechanics`. Extend only that elicitation predicate to accept server
`protocol_mechanics` when the requesting Agent is Protocol and its Task schema is v2. Coordinator,
Modeling, schema-v1 Protocol, unknown servers and every other interactive request remain declined;
the exact preflight tool set still limits this accepted server to
`verify_scoped_retrieval_fallback`. Tests cover each role/schema branch, sanitized evidence and the
existing unknown-server fail-closed behavior. Repeat the same production Protocol-only success and
verifier-error paths before the next baseline.

### B32-08 exact verifier tool argument contract

The accepted Agent-turn call still rewrote a separately valid proof because the private MCP tool
advertised only an unconstrained arbitrary-object input schema. Freeze its input schema to the exact
ten top-level proof members consumed by the verifier: mode, initial/final modeling contexts,
workspace context, Batch inventory/details, entity read, statement read, candidate assertions and
statement lineage. Require all ten, reject extra wrapper fields, and describe every response member
as the unmodified full `{ok,data}` object; arguments are these fields directly, never a nested
`proof` projection. The verifier implementation and semantic gates do not change. Tool-list/schema
tests plus the same Protocol-only real valid-proof and invalid-proof turns must prove faithful
success and fail-closed behavior before another baseline.

### B32-09 deterministic Protocol terminal verifier gate

Exact instructions and schema cannot make model routing itself authoritative. For the schema-v2
Protocol Agent in a frozen `scope.mode=create` run, Adapter therefore derives a retrieval episode
from actual completed App Server `mcpToolCall` items. A query is eligible only when its captured
arguments have `scope_mode == "ontologies"` and `ontology_ids` is a non-empty list of non-empty
strings; a project-scoped, empty, missing or ill-typed query neither creates nor replaces an episode.
A completed eligible `ontology_platform/query_semantic_context` `{ok:true,data}` response is
mechanically complete only when `result_status == "matched"`, `data.recall.completeness ==
"complete"`, the aggregate and both page `truncated` flags are false, both next cursors are null,
and every primary/related item belongs to the requested Ontology set with complete required
Evidence and lineage. In particular, asserted items require `evidence_status == "supported"`, all
returned items require `lineage.status == "complete"`, and aggregate/item warnings must not include
`evidence_missing`, `lineage_missing`, `lineage_partial`, `lineage_truncated`, or
`legacy_lineage_unavailable`. A missing or malformed required field fails closed as incomplete. That
complete generic path permits terminal reporting without a verifier. An error envelope, no-match,
degraded completeness, truncation, cursor, scope leakage, or incomplete Evidence/lineage instead
arms an eligible fallback episode.

The armed episode is satisfied only by a later actually completed
`protocol_mechanics/verify_scoped_retrieval_fallback` MCP item. Elicitation approval, an in-progress
item, a verifier before the query, or a verifier belonging to an earlier episode is insufficient.
The verifier outcome is deliberately not interpreted by Adapter: either its completed success or
tool/protocol error satisfies the attempt obligation, while Protocol still owns success versus
fail-closed conflict. A later eligible generic query replaces the episode. A successful
`submit_modeling_batch(mode=apply_atomic)`, `run_semantic_validation`, or
`run_semantic_reasoning` completed after a retrieval result moves the gate to a separate
`query_required` state. That state blocks terminal reporting, cannot be satisfied by a verifier, and
can be replaced only by a later completed eligible generic query. Failed operations and dry-runs do
not invalidate retrieval because they do not establish new applied/derived semantic state. Episode
state survives turn boundaries so the required Modeling terminal-handoff can be delivered after
retrieval without making valid evidence stale merely because App Server opened a new turn.

Before forwarding `report_task_result`, Adapter rejects an armed unsatisfied eligible episode or
`query_required`, using a fixed safe retryable error before broker delivery. It does not gate v1,
other roles, non-create scope, ordinary team messages, preflight, a complete generic path, or a
Protocol path that has not yet entered generic retrieval/state change. Runtime evidence records only
sanitized state transitions, tool identity, episode number and disposition, never arguments or raw
results. Unit tests cover the
complete generic path, every role/schema/scope branch, elicitation-only and unfinished items,
ordering, episode replacement, Evidence/lineage incompleteness, mutation invalidation,
query-required/verifier non-bypass, cross-turn satisfaction, verifier success and error completion,
and retry-after-attempt. A production Protocol-only fixture then proves incomplete generic retrieval
is rejected at terminal, the verifier attempt is actually completed, and the correlated success or
conflict terminal report is accepted.

### B32-10 bind the gate to the production Team Transport path

Round39 proved that normal Agent MCP calls do not use Adapter's dynamic-tool transport helper. The
Agent-local `transport_mcp.py` process forwards `report_task_result` directly to
`TeamTransportBroker.report`, so B32-09's state machine observed the query but its pre-broker guard
was disconnected from the production call. The repair keeps the state machine and moves the single
authoritative enforcement point to the broker boundary.

`RuntimeAdapter` exposes a default-false `terminal_report_blocked(agent_id)` hook. `TeamRunner`
passes that bound hook into a new optional Broker terminal guard; test adapters and direct Broker
users remain allow-by-default. `TeamTransportBroker.report` invokes the guard before acquiring or
changing terminal-result state. Only an absent guard or the exact boolean `false` permits the report;
true, a non-boolean result, or a callback exception raises one Broker-owned fixed retry error, so
callback text or exceptions cannot become Agent-visible data.

The Codex implementation resolves the exact Agent. For the production Agent-local stdio path, its
Broker callback first takes that Agent's App Server I/O lock, non-blockingly drains and applies all
already ordered pending stdout notifications, then reads retrieval state. Normal foreground drains
and `_rpc` reads use the same lock, preventing two threads from consuming or reordering one App
Server stream. State transitions and guard reads additionally share the per-Agent state lock. This
synchronous drain barrier closes the race in which Agent-local transport reaches the Broker during
the foreground loop's 100 ms polling interval after query completion.

The legacy Host dynamic-tool path is already invoked synchronously while dispatching one ordered
App Server notification; acquiring the same I/O lock again from the Broker thread would deadlock.
That helper therefore adds one host-internal top-level synchronization marker to its private Broker-
socket request. The immutable Agent-local stdio forwarder never creates that marker, and ordinary
tool arguments cannot set a top-level socket-request member. Broker passes the marker only as a
boolean `already_synchronized` guard input: Codex skips stdout drain for that call, because all prior
notifications have already been applied, but still reads the same state lock. No marker can bypass
the state decision itself. The helper otherwise delegates to the same Broker guard and policy.

This connects the actual stdio MCP -> Unix socket -> Broker route without exposing retrieval state
to the Agent-local process, changing the MCP schema, or placing business semantics in Broker.
`send_team_message`, v1, other roles, non-create runs, idle/pre-query conflict, complete generic and
fallback-satisfied states remain unaffected. Broker tests prove guard-before-mutation and fixed error;
Runner tests prove the adapter hook is wired; Codex isolation proves single-reader I/O locking,
pending-notification drain-before-guard, the internal-marker boundary, lock-consistent states and
both normal-socket and dynamic-helper behavior without deadlock. Production Protocol-only acceptance
must observe, in
order, the incomplete query transition, real report MCP rejection plus `terminal_blocked`, a real
completed verifier item, and a later accepted broker terminal. The complete-generic fixture also
retains an in-memory mechanical summary of every completeness member before raw response disposal,
so an inconclusive result has an actionable cause rather than another unclassified fallback.

The first blocker is classified as `modeling-quality`, `platform-contract`,
`collaboration/routing`, or `runtime/infrastructure`. Cleanup problems are appended without
overwriting the primary category. Configuration and visibility failures occur before semantic
start. Missing semantic evidence is FAIL or INCONCLUSIVE, never reconstructed by a new launcher.

## Acceptance criteria

1. Task v1 regression remains unchanged; Task v2 fails closed and stages only role-authorized
   frozen sources with exact hashes.
2. One fresh base three-Agent run starts within the requirement gate and only Protocol receives the
   declared write MCP surface.
3. Direct Modeling-to-Protocol semantic handoff, Protocol feedback, and continuing Coordinator
   question/answer evidence exist.
4. Formal immutable Batch dry-run/apply, Shape negative, workspace advancement,
   `validation.conforms=true`, `reasoning.consistent=true`, and either a complete governed generic
   query or an eligible `fallback_required` episode with native verifier `complete=true` satisfy the
   frozen L3 semantic gate; the candidate-required-assertions/lineage contract is also complete.
5. Build Session, Lease, Runtime, credentials, secrets, and failure cleanup satisfy the frozen
   lifecycle contract.
6. The successful non-empty scope is retained and the five-field immutable handoff matches direct
   platform state and is published only after independent semantic PASS.
7. Automated regression, real run, fresh independent Agent acceptance, service health, and
   documentation synchronization PASS on the final runtime-affecting baseline.

## Future productization

No background orchestration, retry service, long-term audit store, generalized source registry,
automatic answer broker, remote Runtime, management UI, cross-machine coordination, or automatic
failed-written-scope deletion is introduced. R2.3-003 owns existing-scope continuation and final
successful-scope cleanup; R2.3-004 owns Pi.

### B32-11 — Protocol mechanical binding clarification

The platform compiler intentionally remains unchanged. For an object predicate that must be both a
relation predicate and a Shape path, Protocol creates one `create_property` with `object_class_id`,
then binds `create_relation.relation_type_iri` to that formal `/property/{id}` output and Shape
`path_id` to the same formal property ID. A relation-type and property sharing an ID are distinct
compiler resources (`/relation-type/{id}` versus `/property/{id}`); Protocol must return a concrete
translation conflict rather than submit that divergent combination.

The native retrieval fallback proof's ten direct arguments include `mode`, whose only valid literal
is `create`. The wrapper schema and its local validator reject `fresh_create` or any other value
before the native verifier, avoiding an avoidable `-32010` platform-contract failure. This corrects
the forward protocol contract only; Attempt15's recorded `fresh_create` failure remains unchanged.

### Closure-plan revision — failed run `r23002-real-20260801r`

> Historical Round 47 wording retained for append-only trace; Round 48 below supersedes its active
> gate and causal interpretation.

The failed run remains historical evidence, not a source of reconstructed proof. Its closeout and
any next producer are separate phases; neither may mutate the other phase's evidence.

1. **Evidence provenance preflight.** Before terminal classification or any new start, an
   independent Protocol-only preflight must locate, hash, freeze, and pass through the original
   unmodified formal `initial_modeling_context` from run `r`. It must also uniquely recover the
   exact original `candidate_required_assertions` through an attributed Modeling candidate delivery
   and the correlated Protocol evidence that consumed it. All final-context, workspace, Batch,
   read, and lineage inputs are newly obtained read-only responses. A missing artifact, competing
   candidate, broken correlation, changed digest, or any ambiguity is **INCONCLUSIVE**: stop before
   terminal classification, repair authorization, reservation, or a new semantic start. Do not
   synthesize a zero context or select assertions by interpretation.
2. **Failed-run closeout.** Once provenance passes, first perform the read-only admin ownership
   precheck: reread the owned Project/Ontology, workspace, Build Session, every Attempt, and Lease;
   prove no Attempt is `applying` or `recovering`. The ledger terminal classification is then the
   first ledger event. Closeout may save one explicit failure checkpoint at the current returned
   Session revision, then cancels using the returned revision, rereads cancelled Session/released
   Lease, revokes the old model key by ID, and preflight-reads that key plus every temporary admin
   key. Preserve only necessary non-secret evidence before destroying all three runtime `auth.json`
   files, private `config.toml` files, and temporary credentials. It never reacquires, completes, or
   separately releases the Lease.
3. **Lifecycle proof before repair.** Before `authorize_repair`, an independent tester must pass a
   narrow runtime-lifecycle fix or operating unit that starts continuous monitoring before the
   producer command, retains it through terminal and cleanup, and survives parent/PM turn
   boundaries. Its no-semantic-start proof is exactly monitor-start, monitored command lifecycle,
   monitor-stop, and secret destruction; it creates no Platform scope, key, Session, Lease,
   reservation, or semantic start.
4. **Irreversible ordering.** The only permitted sequence is: `r` terminal classification, `r`
   cleanup proof, unique tranche 8 `+2`, independent lifecycle-repair evidence, fresh
   baseline/repair authorization, and fresh reservation/start. For a fresh producer, all three
   Agents first complete and settle; then Session/Lease/key/runtime-secret cleanup completes,
   evidence freezes, the same independent tester passes Phase A, the deterministic handoff publisher
   runs, that tester opens a fresh Session for Phase B, and only then can final PASS be declared.

The current local `r` tree records `state=PAUSED` and sanitized event/delivery evidence, but no
retained original formal initial-context response or uniquely bound assertions artifact. This is a
known preflight blocker, not permission to infer either value.

### Terra xhigh feasibility audit — do not switch

The existing Team Profile/Runtime interface cannot pin all three Agents to
`gpt-5.6-terra` with `reasoning_effort=xhigh`: the profile parser accepts only homogeneous
`runtime: codex`; package runtime validation consumes only `runtime.codex.sandbox`; Profile
`parameters` has no runtime consumer; and Codex's private `config.toml`, `namespace_command`, and
`thread/start` mapping emit no model or reasoning-effort setting. The inspected failed-run private
configs likewise contain no such setting. This is not a low-complexity configuration change and
would require an explicit Profile/Runtime contract plus launch-mapping implementation and tests.
Do not switch model or reasoning effort in this closure plan.

### Round 48 plan revision — settled failed-run gate, repair evidence, and ordering

This section is the current closure contract. It supersedes only the active closure sequencing and
causal wording above; all earlier review and test-round entries remain append-only historical
evidence. No code, runtime, ledger, key, Session, or delivery-record change is part of this
documentation revision.

#### P0 provenance gate and settled causal classification

P0 is a provenance gate, not a reason to skip failed-run closeout. The original zero initial formal
envelope is recoverable and must be frozen byte-for-byte with canonical SHA-256
`4e66b6d21d4b8e9cff9c279d965b638d8dd849a25a692b964a04d1e80ad3a50f`. The unique
`candidate_required_assertions` artifact is missing. Therefore P0 blocks the old run from PASS and
blocks repair authorization or a new producer start until that candidate artifact is independently
repaired, but it does not block recording the mandatory terminal failure and completing the failed-run
closeout below. No synthetic zero envelope, inferred assertion selection, or recovered candidate
may be treated as a PASS substitute.

This explicitly corrects the earlier active wording that no original formal initial-context response
was retained: the zero envelope is recoverable at the digest above; only the uniquely bound candidate
assertions artifact is missing.

Run `r` receives exactly one immutable terminal classification:
`failure_category=runtime/infrastructure` and `complete_modeling_quality_result=false`. The causal
record cites the recoverable validation errors returned by the `max_depth=10` lineage calls at
`00:14:46-00:14:47`, interruption of the active Protocol and Modeling turns at `00:14:48`, zero
`report_task_result` calls, `state=PAUSED`, and later disappearance of run-specific processes
without normal cleanup. `max_depth`, candidate provenance, and verifier gaps remain explicitly
unresolved secondary facts; none is a competing terminal classification cause and none may be
silently promoted to `modeling-quality` or `platform-contract`.

#### Mandatory failed-run closeout

The closeout is ordered and append-only:

1. Freeze the non-secret gap list and all non-secret failed-run evidence, including the P0 digest,
   missing-candidate fact, lineage errors, interruption/process-loss observations, and the current
   state/receipt hashes.
2. Append one `terminal_failure` record with the exact classification above. This is the first
   terminal ledger event for `r`; no replacement or second classification is permitted.
3. Reread admin ownership, Project/Ontology identity, workspace, Session, every Modeling Batch
   Attempt, and Lease. Prove that no Attempt is `applying` or `recovering` before any cancellation.
4. At the current revision returned by that reread, **must** save one failure checkpoint. Its reason
   is the terminal runtime/infrastructure failure and it lists the unresolved candidate, lineage,
   verifier, and process-loss items. The checkpoint is retained even when those items are not the
   classification cause.
5. Cancel the Session using the checkpoint's returned revision, then reread `cancelled` Session and
   released Lease state. Closeout must not reacquire, complete, or issue a separate Lease release.
6. Enumerate the old Project model key by its exact ID and revoke it. Enumerate and revoke every
   temporary/bootstrap admin or read key, retaining direct per-key proof of revocation; a launcher
   summary is insufficient.
7. Retain the non-secret failed-written scope and evidence as required for the historical attempt;
   it is not a handoff candidate and is not deleted as part of this closeout.
8. Destroy all three role/runtime `auth.json` files, private `config.toml` files, and temporary
   credential material, and directly prove their absence. Secret destruction occurs only after the
   non-secret evidence freeze and key-revocation proof.

If a required closeout observation is unavailable, record that gap without changing the immutable
classification or inventing a successful cleanup. The old run remains non-PASS until P0 and every
closeout assertion is repaired and independently rechecked.

#### Immutable Modeling-to-Protocol required-assertions contract

The repair freezes a concrete contract named `candidate-required-assertions/v1`:

- Modeling owns a nonempty, platform-neutral ordered set of required statements. Each statement is
  a canonical asserted-data quad representation (`subject`, `predicate`, `object`, `object_kind`,
  optional datatype/language, and `source_graph_iri`), with no platform-generated resource IDs.
- The candidate envelope carries `candidate_revision`, the originating `delivery_id`, the exact
  `reply_to_delivery_id` chain, the canonical digest of the frozen statement set, and the nonempty
  statement set. The revision is uniquely bound to that delivery/reply chain and digest; a later
  candidate is a new revision, never an in-place edit.
- After platform receipts are available, Protocol translates that same frozen revision into a
  nonempty, duplicate-free canonical asserted-data quad set. It does not select, infer, delete, or
  add semantic assertions. Every quad has exactly one computed platform fact ID, and every computed
  fact ID has exactly one matching `get_ontology_lineage(target_type=statement, target_id=...)`
  response. Lineage must bind the same quad, Ontology, data graph, and candidate digest.
- `max_depth` is an integer in the inclusive range `0..5`. Values outside that range, duplicate
  quads or fact IDs, empty sets, extra or unbound lineage responses, missing lineage, revision/digest
  drift, wrong graph/ontology, and any candidate-to-Protocol mismatch are rejected fail-closed.
  Delivery performs only mechanical correlation and digest checks; it never chooses required
  assertions or semantic meaning.
- The native verifier accepts only `mode=create` for this fresh-create proof and rejects a vacuous
  proof (empty candidate assertions, empty asserted-data quads, or no one-to-one lineage). A
  `complete=true` verifier result is acceptable only after the observed eligible
  `fallback_required` retrieval episode and its complete native verifier item. The direct generic
  query path with `complete=true` remains the alternative success path; it must not be replaced by
  a verifier call or require both alternatives.

#### Split no-semantic-start repair evidence and baseline delta

Before any repair authorization, the independent tester executes two separate, no-semantic-start
tests. They share no business sources, StartLedger entry, or producer semantic start:

1. **P2-monitor operating unit.** Start a continuous monitor before a harmless producer-command
   lifecycle, keep it attached through terminal/cleanup and parent/PM turn boundaries, stop it only
   after the command lifecycle, and prove destruction of temporary secrets. Evidence binds the exact
   monitor command, argv, opened-descriptor contract, the
   `modeling_team/foreground_monitor.py` SHA-256, start/stop lifecycle
   timestamps, and an append-only evidence path. The implementation paths are
   `modeling_team/foreground_monitor.py` and
   `modeling_team/references/p2-monitor-contract.json`; both SHA-256 values are retained. It creates
   no Project, Ontology, key, Session,
   Lease, reservation, or semantic start.
2. **P2-Protocol contract preflight.** Through the production Codex Adapter, bwrap namespace,
   private config, app-server, and native MCP RPC, create only a minimal ephemeral Project/Ontology,
   Protocol key, Build Session, and Lease. Use a non-business candidate fixture to prove the
   immutable candidate/revision/digest, canonical asserted-data quad, one-to-one fact ID, exact
   lineage, `max_depth=0..5`, duplicate/extra/drift rejection, native `mode=create` rejection of a
   vacuous proof, and `complete=true` only on the observed eligible `fallback_required` path.
   Prove full Session/Lease/key/Project cleanup and zero residuals directly. Do not deliver business
   sources, write StartLedger, or start a Producer model.

The P2-Protocol fixture repairs and verifies the producer-side candidate-artifact contract; it does
not rewrite `r` or fabricate its missing historical artifact. A fresh producer may proceed only when
that contract repair is represented in the second fresh baseline and the P0 gate's missing-artifact
condition is thereby resolved for the new run. Focused checks cover the monitor lifecycle/evidence
contract, candidate revision/digest preservation, one-to-one lineage and max-depth bounds, native
verifier mode/fallback routing, and zero-residual cleanup.

The minimal fresh baseline-manifest delta adds only the P2 monitor command/argv/descriptor contract,
the `modeling_team/foreground_monitor.py` and `modeling_team/references/p2-monitor-contract.json`
SHA-256 values, lifecycle/evidence path, and the Protocol candidate/verifier contract plus its
production launch/tool-schema hashes. Generate two independent fresh manifests after both P2 tests:
`baseline-1` is frozen and checked against the repair files; `baseline-2` is regenerated from the
clean tree and must have the same canonical content/hash before authorization. Any unexpected file,
hash, command, descriptor, or evidence-path drift fails closed. A future implementer changing a
symbol must first run the AGENTS.md-mandated GitNexus upstream impact analysis and warn on HIGH or
CRITICAL risk; this round makes no symbol edit and therefore requires no code-impact result.

#### Irreversible ordering to the next producer and final gates

The only permitted sequence is:

`r` terminal classification -> `r` mandatory closeout -> independent P2 monitor **and** P2 Protocol
repair evidence PASS -> unique continuing-authorization **tranche 8 +2** -> two fresh matching
baselines -> repair authorization bound to `r` and `baseline-2` -> reservation/start -> fresh
producer with all three Agents completed and settled -> successful Session/Lease/key/runtime-secret
cleanup and evidence freeze -> the same independent tester's Phase A PASS -> deterministic handoff
publication -> that tester's fresh Session Phase B -> final repository/runtime/requirement gates.

No tranche, baseline, repair authorization, reservation, or semantic start may move earlier in this
sequence. The fresh producer must never reuse `r`'s scope or evidence. F1 remains unchanged: do not
switch Team model or reasoning effort because no supported configuration surface exists and that
change is outside this narrow repair.

### Round 49 plan revision — accepted High findings and implementable proof contract

Round 48 remains immutable history. This section is the current active correction for the five
accepted High findings; it does not authorize implementation or any runtime mutation. It supersedes
Round 48 only where the proof shapes, lifecycle evidence, baseline computation, or stable input list
below are more precise.

#### H1 — platform-neutral candidate and deterministic digest binding

`candidate-required-assertions/v1` is platform-neutral at the Modeling boundary. Every Modeling item
has exactly these semantic fields:

```json
{
  "graph_role": "asserted_data",
  "subject": "<semantic subject>",
  "predicate": "<semantic predicate>",
  "object": "<semantic object>",
  "object_kind": "<iri|literal|...>",
  "object_datatype": null,
  "object_language": null
}
```

`object_datatype` and `object_language` are always present as a string or JSON `null`; every other
field is forbidden. Modeling never emits `source_graph_iri`, platform resource IDs, generated IRIs,
fact IDs, workspace versions, or other platform receipt values. `graph_role` must be exactly
`asserted_data`.

The canonical JSON function is UTF-8 encoded `json.dumps(value, ensure_ascii=False,
sort_keys=True, separators=(",", ":"))`; booleans/nulls use JSON literals and no whitespace is
permitted. A statement's canonical bytes are its canonical JSON bytes. The statement list is sorted
lexicographically by those UTF-8 bytes; duplicate canonical bytes fail closed. The semantic payload
is exactly `{"schema_version":"candidate-required-assertions/v1","statements":[<sorted items>]}`
and `semantic_digest` is SHA-256 of its canonical JSON UTF-8 bytes.

The candidate binding payload is exactly
`{"schema_version":"candidate-required-assertions/v1","candidate_revision":<string>,
"delivery_id":<string>,"reply_chain":[<delivery IDs in order>],"semantic_digest":<hex>}`.
`candidate_digest` is SHA-256 of that canonical JSON UTF-8 payload. A revision, delivery ID, reply
chain, or semantic digest change therefore changes the candidate digest; no semantic digest may drift
between Modeling, Protocol, or verifier evidence.

Only after formal workspace receipts are read may Protocol resolve `graph_role=asserted_data` to the
single final `source_graph_iri`. Protocol materializes each exact quad with the original semantic
fields plus that resolved graph IRI. Materialized quads use the same canonical JSON function and
ordering. `materialized_digest` is SHA-256 of the exact canonical payload
`{"candidate_digest":<hex>,"quads":[<sorted materialized quads>]}`. Protocol computes platform
fact IDs from those materialized quads; Modeling never chooses or supplies them. The verifier
recomputes all three digests and rejects empty, duplicate, graph-role/source-graph, ID, or binding
drift before considering lineage or retrieval completeness.

#### H2 — exact native proof shape and nested binding

The native verifier continues to receive exactly these ten top-level fields, with no `proof` wrapper
and no additional top-level member, in the canonical order shown for documentation and tests:

```text
mode
initial_modeling_context
final_modeling_context
workspace_context
batch_inventory
batch_details
entities_read
statements_read
candidate_required_assertions
statement_lineage
```

`candidate_required_assertions` is a strict object with metadata/bindings and nonempty arrays:

```json
{
  "schema_version": "candidate-required-assertions/v1",
  "candidate_revision": "<string>",
  "delivery_id": "<string>",
  "reply_chain": ["<delivery ID>"],
  "semantic_digest": "<sha256>",
  "candidate_digest": "<sha256>",
  "items": ["<the sorted platform-neutral statements>"],
  "materialized_digest": "<sha256>",
  "materialized_quads": ["<the sorted exact quads with source_graph_iri>"]
}
```

`statement_lineage` is a strict object carrying the same candidate/materialized binding, an integer
`max_depth` in `0..5`, and nonempty records:

```json
{
  "schema_version": "candidate-required-assertions/v1",
  "candidate_revision": "<same>",
  "delivery_id": "<same>",
  "reply_chain": ["<same>"],
  "semantic_digest": "<same>",
  "candidate_digest": "<same>",
  "materialized_digest": "<same>",
  "max_depth": 0,
  "records": [
    {"fact_id": "<computed>", "quad": "<same materialized quad>",
     "response": {"ok": true, "data": "<full lineage envelope>"}}
  ]
}
```

Wrapper and verifier validation is strict at both levels: reject missing/extra members, empty items
or records, duplicate statements/quads/fact IDs, extra or unbound lineage, wrong graph/Ontology,
fact/quad mismatch, max-depth outside `0..5`, and any candidate/materialized revision, chain, or
digest mismatch. The one-to-one rule is exact: each materialized quad has one computed fact ID and
each fact ID has exactly one matching lineage response. The direct generic `complete=true` path stays
an alternative success path; this candidate/verifier proof is required only for an observed eligible
`fallback_required` episode, never for a direct complete generic result.

Planned implementation and tests are explicit: update `modeling_team/protocol_retrieval_mcp.py` to
advertise and reject the exact ten-field/nested schema, update
`modeling_team/protocol_mechanics.py` to implement the canonical algorithms and cross-binding, and
update `modeling_team/agent-packages/modeling/instructions.md`,
`modeling_team/agent-packages/protocol/instructions.md`, and the stable references named in H6.
Focused tests extend `modeling_team/tests/test_protocol_retrieval_mcp.py` and
`modeling_team/tests/test_r23002.py` with positive and every listed negative shape/digest case.

#### H3 — same-run double baseline computation

After both P2 tests and the unique tranche-8 authorization, choose one fresh prospective run ID and
pass that **same** ID and the **same stable file set** to two independent `_baseline_manifest`
computations. Both computations occur before any reservation or semantic start and neither writes
StartLedger, creates a Project/key/Session/Lease, or reads ephemeral fixture/evidence data. Compare
the complete manifests and final hash byte-for-byte; any missing, extra, reordered, or changed stable
entry fails closed. The prospective run ID is an external binding argument used identically in both
calls, not an ephemeral file entry; it must not make the stable-file digest depend on a PID, fixture,
credential, evidence path, or runtime output.

#### H4 — real foreground P2 monitor lifecycle without an R2.3-002 semantic start

P2-monitor must run the real foreground `TeamRunner` -> `CodexRuntimeAdapter` -> app-server ->
Team Transport/Broker -> ordered settlement -> secret-destruction path under the proposed persistent
operating unit. The monitor starts before the command, remains attached across at least one parent/PM
turn boundary and through all three Agent terminal/settlement and cleanup events, then stops only after
secret absence is proven. Its exact command/argv, descriptor ownership, lifecycle states, boundary
marker, script digest, and append-only evidence path come from
`modeling_team/references/p2-monitor-contract.json`, not from a generated fixture.

Reuse `modeling_team/profiles/base-three-agent.yaml` with
`modeling_team/tasks/base-capability-smoke.yaml` (the closest accepted R2.3-001 nonbusiness smoke),
or an equivalent production-lifecycle fixture with the same prohibitions. This run is not an
R2.3-002 semantic start because it is schema-v1 mechanics-only, delivers no R2.3-002 business
sources/candidate, forbids Modeling Items/Batch/Build Session/Lease, and performs no StartLedger
semantic reservation or marker. If the production foreground path needs owned ephemeral auth/config
or other resources, create them under the monitor's ownership and prove full cleanup; those
mechanics resources do not become an R2.3-002 semantic run. When such resources are used, retain
direct API and database zero-residual proof alongside the monitor lifecycle evidence.

#### H5 — real transport correlation and complete Protocol fixture cleanup

P2-Protocol first traverses the real `TeamTransportBroker`/production stdio path with a synthetic
nonbusiness Modeling candidate: capture one `delivery_id`, the exact `reply_to_delivery_id` chain,
Protocol's correlated receipt, and the terminal handoff before invoking the production
Codex Adapter+bwrap+app-server+native MCP verifier. A byte-equivalent production stdio proof is
allowed only if it preserves the same envelope bytes and broker correlation checks; an in-process
direct function call is not evidence.

The fixture explicitly creates and lists by ID a bootstrap-admin key, a read-only key, and a Protocol
key (plus any Project model key required by the production scope). It then runs the candidate,
materialization, lineage, and native `mode=create`/eligible-fallback verifier checks through the
real path. Cleanup directly revokes every recorded key ID, cancels/completes the Session according
to its state, releases the Lease, deletes the owned temporary Project/Ontology, destroys secrets,
and proves through both API reads and direct database residual counts that temporary Project,
Ontology, Session, Lease, and all key rows are zero. The fixture has no business sources, no
StartLedger semantic start, and no Producer semantic start.

#### H6 — stable baseline inputs and omission/drift tests

The planned `_baseline_manifest` delta is implementable and exact. Stable code/descriptor/schema
inputs to hash are:

- `modeling_team/runner.py` (`TeamRunner._baseline_manifest` and baseline binding);
- `modeling_team/contracts.py`;
- `modeling_team/protocol_mechanics.py`;
- `modeling_team/protocol_retrieval_mcp.py`;
- `modeling_team/protocol_mcp_launch.py`;
- `modeling_team/transport_mcp.py`;
- `modeling_team/runtimes/codex.py`;
- `modeling_team/agent-packages/modeling/instructions.md`;
- `modeling_team/agent-packages/protocol/instructions.md`;
- new stable descriptor `modeling_team/references/candidate-required-assertions-v1.json`;
- new stable descriptor `modeling_team/references/native-retrieval-proof-v1.json`;
- new stable descriptor `modeling_team/references/p2-monitor-contract.json`.

The candidate descriptor freezes the exact semantic field scope and digest algorithms; the native
proof descriptor freezes the ten top-level and nested JSON shapes; and the monitor descriptor freezes
the command/argv, descriptor/lifecycle contract, parent-PM boundary marker, and evidence handoff.

The existing `modeling_team/references/modeling-batch-item-contract.json`, Profile, Task, Skills,
and source entries remain governed by the existing baseline rules; they are not replaced by these
descriptors. `_baseline_manifest` must include the listed stable paths and their SHA-256 values, fail
closed when any listed file is missing or an unexpected stable contract/monitor file is omitted, and
make any byte drift change the baseline hash. Focused tests extend `modeling_team/tests/test_runner.py`
and `modeling_team/tests/test_r23002.py` to prove omission, addition, byte drift, and same-run
double-computation rejection. `modeling_team/tests/`, synthetic candidate fixtures, ephemeral task
answers, evidence files, runtime directories, credentials, descriptor FDs, and PIDs never enter the
baseline file set or digest.

The monitor command/argv and lifecycle contract are read from the stable
`p2-monitor-contract.json`; generated command lines, evidence locations, process IDs, and temporary
fixture values are evidence only and never baseline inputs. Any implementation that hard-codes a
different command or silently drops one of the three descriptors fails the focused baseline tests.

The exact sequence remains: `r` terminal classification -> mandatory closeout -> real P2-monitor and
P2-Protocol PASS -> unique tranche 8 `+2` -> same prospective run ID/two matching baselines -> repair
authorization -> reservation/start -> three Agents completed/settled -> success cleanup/evidence
freeze -> same independent tester Phase A -> deterministic handoff -> Phase B -> final gates. F1
still forbids switching Team model or reasoning effort.

### Round 50 plan revision — final runtime boundary, schema names, and external evidence binding

Round 49 remains retained plan history. This section records the Round 50 active correction for the
final review findings and supersedes its literal zero-scope/key wording and singular read-field
spelling. Round 51 below further supersedes this section only for P2 path execution and deletion
cleanup; its candidate/proof schema, baseline, external binding, and ordering remain active. No
implementation, runtime, ledger, key, Session, semantic-start, or delivery-record mutation is
authorized by this documentation change.

#### P2 resource boundary and key-history contract

Both P2 tests are no-business, no-R2.3-002-StartLedger-reservation/`semantic_start`, no-retained-
product-scope evidence. P2-monitor is the only path that exercises the real foreground CLI/TeamRunner/
Codex Adapter/app-server/Team Transport/Broker/MCP/settlement chain; P2-Protocol is explicitly
TeamRunner-free and uses the production Adapter/Transport path described in Round 51. Either path may
create at most one uniquely owned ephemeral Project/Ontology, bootstrap-admin key, read key,
model-or-Protocol key, Build Session, and Lease—but only when its production path actually requires
them. Before deleting the ephemeral Project, freeze a first-stage non-secret artifact covering every
project-scoped read/model/Protocol key's exact ID, `revoked_at`, non-active status, cancelled Session,
Lease auto-release, ownership, cleanup receipts, and no in-flight Attempt. It must also record the exact
org-scoped
bootstrap-admin key ID as `ACTIVE`, solely to authorize the upcoming authenticated Project DELETE, and
exclude that key from the first-stage non-active assertion. Use that active org-admin credential for the
formal DELETE; then verify Project/Ontology absence, project-scoped active residuals zero, and existing
FK cascade behavior. Immediately revoke the org-admin key and freeze a second-stage artifact with its
exact ID, `revoked_at`, non-active status, and retained org-admin audit row. The aggregate cleanup
evidence combines both stages and proves every created key ended non-active. No new deletion credential,
direct DB delete, hard-delete, migration, archive, detach, or generalized history-retention
productization is allowed; project-scoped key/Session/Lease rows may cascade-delete and need not remain.
This supersedes the earlier literal “P2 creates no scope or key” and generic history-retention wording.

#### Exact candidate and native proof schema

The platform-neutral Modeling item fields are exactly:

```text
graph_role, subject, predicate, object, object_kind, object_datatype, object_language
```

`graph_role` is exactly `asserted_data`; datatype/language are string or JSON `null`. `source_graph_iri`,
platform IDs/IRIs, fact IDs, workspace versions, receipt members, and unknown fields are forbidden.
The canonical serializer is UTF-8 `json.dumps(value, ensure_ascii=False, sort_keys=True,
separators=(",", ":"))` with no whitespace. Items sort lexicographically by canonical JSON UTF-8
bytes; duplicate bytes fail. `semantic_digest` hashes exactly the canonical object
`{"schema_version":"candidate-required-assertions/v1","statements":[sorted items]}`. The
candidate binding fields are exactly `schema_version, candidate_revision, delivery_id, reply_chain,
semantic_digest`; `candidate_digest` hashes that canonical binding object, preserving reply-chain
delivery order.

After formal receipts/reads, Protocol alone resolves `graph_role=asserted_data` to the final
`source_graph_iri` and materializes exact quads with fields
`graph_role, source_graph_iri, subject, predicate, object, object_kind, object_datatype,
object_language`. Quads sort by the same canonical bytes. `materialized_digest` hashes exactly
`{"candidate_digest":<digest>,"quads":[sorted quads]}`; Protocol computes fact IDs and Modeling does
not provide them.

The native proof has exactly these ten top-level names and no wrapper/extra member:

```text
mode, initial_modeling_context, final_modeling_context, workspace_context,
batch_inventory, batch_details, entities_read, statements_read,
candidate_required_assertions, statement_lineage
```

`candidate_required_assertions` is a strict object with exactly
`schema_version, candidate_revision, delivery_id, reply_chain, semantic_digest, candidate_digest,
items, materialized_digest, materialized_quads`; items and materialized_quads are nonempty sorted
arrays. `statement_lineage` is a strict object with exactly
`schema_version, candidate_revision, delivery_id, reply_chain, semantic_digest, candidate_digest,
materialized_digest, max_depth, records`; `max_depth` is `0..5`. Every record has exactly
`fact_id, quad, response`; `response` is the unprojected full `{ok:true,data:<object>}` lineage MCP
envelope. One record, computed fact ID, materialized quad, and lineage response are one-to-one.
Wrapper and verifier reject missing/extra/empty/duplicate/unbound/mismatched fields, wrong
graph/Ontology, digest/revision/chain drift, and vacuous `mode=create` proof. Direct generic
`complete=true` remains the alternative producer success path; this proof is required only after
the actual fallback episode.

#### Required fallback order and external binding

The P2-Protocol fixture must observe this exact production sequence:

`real Modeling synthetic candidate delivery -> Protocol correlated receipt/reply -> platform
materialization/reads -> completed eligible ontology-scoped query_semantic_context item -> sanitized
retrieval state fallback_required -> later native verifier mode=create complete=true -> Broker terminal
guard/report acceptance -> Protocol runtime cleanup`.

Verifier-before-query, a verifier without prior `fallback_required`, terminal-result-handoff or
Modeling-terminal claims from this fixture, or a manual `sender_id='runner/terminal-result'` fails. The
observer must retain the actual app-server query item and sanitized retrieval-state transition; a
direct native verifier call alone is not acceptance evidence. A producer that naturally obtains direct
generic `complete=true` may use that alternative success path, but the P2 fixture itself exercises
fallback only through Broker guard/report acceptance. The final fresh Producer remains the sole proof
of `candidate/receipt/query/verifier -> Modeling terminal -> real Runner terminal-result-handoff ->
Protocol terminal -> all three completed+settled`.

The independent observer compares the nested candidate's exact `delivery_id`, ordered reply chain,
candidate revision, `semantic_digest`, and `candidate_digest` against the raw Modeling envelope and
Protocol receipt from Team Transport/Broker. It stores only safe IDs/digests. A fabricated, internally
self-consistent new ID/digest that does not match those raw envelopes fails; Delivery never selects
required assertions.

#### Foreground monitor and stable baseline inputs

The persistent monitor implementation is the concrete stable file
`modeling_team/foreground_monitor.py`; its descriptor is
`modeling_team/references/p2-monitor-contract.json`. The descriptor's exact v1 fields/values are
`schema_version="p2-monitor-contract/v1"`, `command="uv"`,
`argv=["run","--project","backend","python","-m","modeling_team.foreground_monitor",
"--contract","modeling_team/references/p2-monitor-contract.json"]`,
`required_stages=["monitor_started","foreground_started","parent_pm_boundary",
"agent_terminal_settled","secret_absent","monitor_stopped"]`, `parent_pm_boundary_count=1`,
`evidence_mode="append_only_run_local"`, `secret_targets=["auth.json","config.toml",
"temporary_credentials"]`, and `resource_policy="at_most_one_owned_ephemeral_scope"`. The
descriptor is the sole source of command, argv, descriptor ownership, lifecycle states, parent-PM
boundary marker, and evidence handoff. Both file hashes and these call sites enter `_baseline_manifest`:

- `modeling_team/runner.py`: `TeamRunner.prepare`, `start`, `_baseline_manifest`, terminal handoff,
  settlement, and cleanup call sites;
- `modeling_team/runtimes/codex.py`: `CodexRuntimeAdapter.start_roster` and `start_task`;
- `modeling_team/transport_mcp.py`: `TeamTransportBroker.send`, `report`, and
  `ack_terminal_handoff`;
- the stable candidate/proof descriptors and Protocol implementation files already listed by
  Round 49.

Omission, addition, or byte drift of the monitor implementation/descriptor or any listed call-site
file fails closed. Generated command lines, evidence paths, credentials, descriptor FDs, fixture data,
and PIDs are evidence only and never baseline inputs. Compute two complete manifests with the same
prospective fresh run ID and same stable files before reservation/start, without ledger writes or
ephemeral reads; entries and hashes must be byte-for-byte equal.

Implementation planning must update `modeling_team/protocol_retrieval_mcp.py` and
`modeling_team/protocol_mechanics.py` for the exact plural `entities_read`/`statements_read` schema,
the nested fields and canonical algorithms; `modeling_team/foreground_monitor.py` and its Runner/
Adapter/Transport call sites for the persistent operating unit; and focused tests for every negative
ordering, external-binding, key-history, and baseline omission/drift case. No code is changed in this
round.

The prior fixed `runtime/infrastructure` classification/mandatory closeout, P2 PASS before tranche 8,
same-ID double baseline, Phase A before handoff, and F1 no Terra/xhigh ordering remains unchanged.

### Round 51 plan revision — separate P2 monitor and Protocol contracts, evidence-first deletion

Round 50 remains retained plan history for the candidate/proof schema, canonical digests, baseline
inputs, external-envelope binding, fallback ordering, and global sequencing. This Round 51 section is
the current active correction for P2 execution boundaries and cleanup; it is not executed and does not
authorize code, runtime, platform, ledger, key, Session, semantic-start, launch-agent, or delivery-record
mutation.

#### P2-monitor — real foreground lifecycle only

P2-monitor uses the existing schema-v1 `modeling_team/profiles/base-three-agent.yaml` and
`modeling_team/tasks/base-capability-smoke.yaml`. The stable `modeling_team/foreground_monitor.py`
command must run the real foreground CLI/TeamRunner/Codex Adapter/app-server/Team Transport/Broker/
settlement/cleanup chain, remain attached through terminal observations and at least one parent-PM
turn boundary, and prove `TeamRunner.drain()` terminal-result-handoff, ack, all-agent settlement,
process persistence, cleanup, and secret absence. This path is the only P2 proof of those real
TeamRunner lifecycle facts; it does not exercise `fallback_required`, native verifier proof, or the
Round 50 business-slice candidate contract. If the existing CLI genuinely requires mechanical platform
state, the monitor may create and clean one uniquely owned ephemeral scope under its direct ownership.
It must not read R2.3-002 business sources or emit an R2.3-002 StartLedger event.

#### P2-Protocol — production transport and fallback contract only

P2-Protocol does not invoke TeamRunner and does not run `modeling_team run`. It constructs the
schema-v2 production `CodexRuntimeAdapter.start_roster` and connects the actual `TeamTransportBroker`,
production stdio transport/private bwrap/app-server/native MCP path exactly as the existing Round 27/32
fixtures do. It may enter `create`/`fallback_eligible`, but must never invoke `TeamRunner.prepare`,
`TeamRunner.start`, StartLedger reserve, or `mark_semantic_start`. The fixture must traverse real Broker
delivery/reply correlation and observe the actual
`query_semantic_context` completion -> sanitized `fallback_required` -> later native verifier ->
terminal guard/report acceptance -> Protocol runtime cleanup sequence. It owns one ephemeral platform
scope and must fully clean it. This proves production Adapter/Transport/Protocol correlation and
verifier mechanics only; it does not prove a Producer run, Modeling terminal, Runner
`terminal-result-handoff`, ack, all-agent settlement, or semantic start. Any TeamRunner invocation,
StartLedger event, or manual `sender_id='runner/terminal-result'` is a negative assertion and fails the
fixture.

#### Shared Session/Lease cleanup and evidence contract

When either path creates a Build Session/Lease, cleanup must execute exactly once in this order:

`admin reread/no in-flight -> failure/terminal checkpoint if applicable -> cancel Session once -> cancel atomically auto-releases all leases -> reread Session cancelled and each Lease state=released with released_at`.

After Session cancellation no explicit Lease-release call is permitted; a second release or
`session_terminal` is not success. Before deleting the ephemeral Project, freeze a first-stage
non-secret artifact covering each project-scoped read/model/Protocol key's exact ID,
`revoked_at`/non-active status, cancelled Session, Lease auto-release, ownership, cleanup receipts,
and no in-flight Attempt. Record the org-scoped bootstrap-admin key's exact ID as `ACTIVE` solely for the upcoming
authenticated DELETE and exclude it from the first-stage non-active assertion. Use that active
org-admin credential for DELETE; verify Project/Ontology absence, project-scoped active residuals zero,
and FK cascade behavior. Immediately revoke the org-admin key and freeze a second-stage artifact with
its exact ID, `revoked_at`, non-active status, and retained org-admin audit row. Aggregate evidence must
combine both stages and prove every created key ended non-active. No new deletion credential, direct DB
delete, hard-delete, archive, detach, migration, or generalized DB history retention is permitted.

The split paths retain all Round 50 candidate/proof/schema/baseline/order rules and remain independent
no-semantic-start evidence. Both P2 paths must PASS before tranche 8, the same prospective run ID and
two matching baselines, repair authorization, or any fresh R2.3-002 semantic start.

### Round 52 plan revision — two-stage key/delete evidence and provenance ownership

Round 51 remains retained plan history for its path split, Session/Lease order, and global gates. This
Round 52 section is the current active correction for the final two accepted High findings; it is not
executed and authorizes no code, runtime, platform, ledger, key, Session, launch, semantic-start, or
delivery-record mutation.

#### Two-stage key/delete evidence

For either P2 path that owns an ephemeral Project, freeze a first-stage non-secret artifact before
DELETE. It must cover every project-scoped read/model/Protocol key with exact ID, `revoked_at`, and
non-active status; Session cancelled; Lease auto-released; ownership; cleanup receipts; and no in-flight
Attempt. It must
also record the exact org-scoped bootstrap-admin key ID as `ACTIVE`, explicitly because that credential
alone authorizes the upcoming authenticated Project DELETE; it is excluded from the first-stage
non-active assertion. Use that still-active org-admin credential for the formal DELETE. Do not create a
new deletion credential, issue a direct DB delete, or hard-delete a row.

After DELETE, verify Project/Ontology absent, project-scoped active residuals zero, and existing FK
cascade behavior. Immediately revoke the org-admin key and freeze a second-stage artifact containing
its exact ID, `revoked_at`, non-active status, and retained org-admin revoked audit row
(`project_id=NULL`). The final
aggregate cleanup evidence combines both artifacts and proves every created key ended non-active;
project-scoped key/Session/Lease rows may cascade-delete and need not remain, while the
`project_id=NULL` org-admin audit row is retained and never hard-deleted.

#### Provenance ownership split

P2-monitor is the only P2 path permitted to claim actual schema-v1 `TeamRunner.drain()` behavior. Its
`foreground_monitor.py` evidence must directly show terminal-result-handoff, ack, all-agent settlement,
and cleanup through the real foreground TeamRunner path. P2-Protocol remains TeamRunner-free schema-v2
production `CodexRuntimeAdapter.start_roster` + Broker/stdio/private-bwrap/app-server/native-MCP. Its
sequence ends at actual `query_semantic_context -> fallback_required -> later verifier complete ->
Broker terminal guard/report acceptance -> Protocol runtime cleanup`. It must not claim or fabricate
Runner terminal-result-handoff, Modeling terminal, ack, or all-three settlement; manual
`sender_id='runner/terminal-result'` is forbidden.

The final fresh Producer remains the v2 provenance proof for
`candidate/receipt/query/verifier -> Modeling terminal -> real Runner terminal-result-handoff ->
Protocol terminal -> all three completed+settled`. P2 PASS cannot substitute for this Producer
evidence. Round 50 schema/digest/baseline/order, Round 51 cleanup/path gates, and the existing F1,
Phase A/handoff/Phase B, and P2-before-tranche-8 rules remain unchanged.

### Round 59 design amendment — retrieval proof v2 before the one remaining semantic start

This is the active minimal repair design for the successful-but-unretrievable run `s`. It supersedes
only Round 50/52's v1 candidate/proof, fallback-completion, evidence, and bounded-read statements.
`s` remains retained `platform-contract BLOCKED` evidence: its existing 48 facts, zero mechanical
per-assertion Evidence binding, 30/30 empty entity/relation evidence arrays, and unconsumed truncated
generic-query cursor are not a PASS and must not be repaired post hoc. This amendment authorizes no
runtime, ledger, start, cleanup, product data, or delivery-record operation.

#### Current minimal scope and explicit non-goals

The repair is a generic Protocol retrieval contract: candidate evidence provenance, receipt-derived
term materialization, platform Evidence binding, mechanical full pagination, and strict native
verifier state. It is not a business-model rewrite. The only implementation/acceptance sequence is
an independent no-semantic-start P2a integration fixture, then the already-authorized single fresh
producer `t`, with no retry on `t` failure and no new tranche.

For this amendment, that fixed one-start cap supersedes the earlier general continuous-authorization
wording: it cannot be used to append an additional tranche. Any start after a failed `t` requires new
explicit user authorization and a separately reviewed refinement.

Future productization is explicitly separate: historical evidence backfill/migration, generalized
evidence governance, Judge, Consumer, mutation suite, recovery workflow, management UI, new backend
tables, extra start budget, or scenario-specific query interpretation are out of scope. The existing
P2 lifecycle/cleanup, `r` closeout, frozen-baseline, Phase A/handoff/Phase B, and Protocol-only-write
contracts stay in force.

#### `candidate-required-assertions/v2` and canonical evidence provenance

Modeling owns exactly one canonical candidate envelope with fields:

```text
schema_version, candidate_revision, delivery_id, reply_chain, semantic_digest, candidate_digest, items
```

`schema_version` is exactly `candidate-required-assertions/v2`. Every sorted, unique `items` member
has exactly:

```text
assertion_id, graph_role, subject, predicate, object, object_kind, object_datatype,
object_language, evidence_citations
```

`assertion_id` is a stable nonempty unique string; `graph_role=asserted_data`; `object_datatype` and
`object_language` are string or null. An item remains platform-neutral: no source graph, platform
IRI/ID, Batch, receipt, workspace version, fact ID, or ontology Evidence individual is allowed.
`evidence_citations` is nonempty, canonical-byte sorted, and contains no duplicate. Each citation has
exactly `source_artifact_sha256, source_locator, excerpt_sha256, owner_answer_id`; the first three are
nonempty strings and `owner_answer_id` is a nonempty released-answer ID or null. The candidate's
semantic digest is SHA-256 of canonical UTF-8 JSON
`{"schema_version":"candidate-required-assertions/v2","statements":[sorted items]}`; candidate digest is
SHA-256 of the canonical binding object containing `schema_version`, `candidate_revision`,
`delivery_id`, ordered `reply_chain`, and `semantic_digest`. v2 has no FNV digest.

Protocol must receive this immutable candidate from attributed Modeling delivery, preserve it byte for
byte, and reject a missing citation before any `apply`. It may not select assertions, infer a source,
or create a zero/placeholder citation.

#### Receipt-derived binding, RDF terms, and Evidence binding

Protocol produces the v2 binding artifacts only from formal Batch receipt/detail/read data. A
`term_bindings` member has exactly:

```text
assertion_id, term_position, candidate_term, binding_kind, client_item_id, batch_id,
resource_output_iri
```

`term_position` is `subject`, `predicate`, or `object`; `binding_kind` is `resource_output` or
`relation_delta`. For `resource_output`, `resource_output_iri` is a nonempty actual applied receipt
`resource_outputs.resource_iri` for the same `client_item_id`/`batch_id`; for `relation_delta`, it is
JSON null and the same `client_item_id`/`batch_id` must bind the exact applied delta quad. Neither
case permits a label-derived IRI. Each materialized quad has exactly the v1 quad fields
`graph_role, source_graph_iri, subject, predicate, object, object_kind, object_datatype,
object_language`, but its IRI terms are actual platform terms derived through those bindings, not the
candidate spelling.

The fixed vocabulary/comparison table is:

| candidate term | actual RDF term | semantic comparison | fact-ID input |
| --- | --- | --- | --- |
| `object_kind=iri` | `<actual platform IRI>` | exact IRI | actual `<IRI>` |
| language literal | `"lex"@language` | lexical form plus language | actual language term |
| RDF 1.1 plain literal | `"lex"` | equal to xsd:string only when lexical form matches and language is absent | actual plain term |
| xsd:string literal | `"lex"^^<http://www.w3.org/2001/XMLSchema#string>` | equal to plain only under the preceding semantic comparison | actual typed term |

Thus the sixteen observed plain literals cannot be silently relabelled `xsd:string`; the comparison
rule is only for semantic correspondence, while canonical quads and fact IDs preserve the exact
platform term.

For every assertion Protocol writes inline or associated Evidence before/with its applied item, then
checks the resulting platform association. `evidence_bindings` is a sorted unique array whose exact
member fields are `assertion_id, evidence_citation_digest, evidence_reference_id, client_item_id,
batch_id, fact_id`. It binds each frozen citation to an actual platform `EvidenceReference` and the
actual fact. Ontology data whose class/label happens to be Evidence is not an EvidenceReference.
`missing_evidence` is a workflow-local blocker before and after apply; this does not change the
backend's generic modeling-batch acceptance semantics.

#### Native v2 proof, complete retrieval, and target-kind lineage

The direct native-verifier arguments have exactly these fourteen top-level members and no wrapper or
extras:

```text
mode, initial_modeling_context, final_modeling_context, workspace_context, batch_inventory,
batch_details, entities_read, statements_read, candidate_required_assertions, term_bindings,
materialized_quads, evidence_bindings, statement_lineage, pagination
```

`materialized_digest` is SHA-256 of canonical
`{"candidate_digest":<candidate_digest>,"term_bindings":[sorted bindings],"quads":[sorted quads]}`.
The independent verifier reconstructs all terms from receipt/delta/read fields, recomputes every
digest/fact ID/Evidence binding, and rejects any missing, ambiguous, duplicate, unbound, label-derived,
or drifting value.

Every lineage record has exactly `assertion_id, fact_id, quad, target, response`. `target` has exactly
`target_kind, target_id`; `target_kind=resource` is required for an ObjectProperty resource and
`target_kind=statement` for a relation fact. A decoration/read-model appearance cannot select the
target kind. The associated full response must be a successful unprojected platform envelope and must
contain the bound `EvidenceReference` association.

`pagination` is a strict object with `schema_version, streams`. Each stream has exactly
`stream_kind, pages`; `stream_kind` is `matches` or `context`. Every page has exactly
`request_cursor, next_cursor, returned_item_ids, truncated, degraded, blocking_warnings, response`.
Protocol consumes every cursor until each stream's final `next_cursor` is null, unions returned stable
item identities across pages, and rejects duplicate-with-different-content. A non-null cursor,
`truncated=true`, `degraded=true`, or nonempty `blocking_warnings` is incomplete; prose cannot override
these fields.

Adapter state may enter `fallback_satisfied` only from a native verifier success envelope with no
`error` member and `data.complete=true` (or its documented structured-content projection). A
`failed` tool item, JSON-RPC `-32602`, any error envelope, absent `data`, or `complete!=true` keeps
`fallback_required`; it cannot pass Broker's terminal guard.

#### Staged acceptance and evidence order

P2a uses a generated-IRI, generic evidence integration fixture and creates no semantic start. It must
prove v2 on representative assertions spanning all 48 fact classes, receipt term bindings, all RDF
term rows, per-assertion platform Evidence, resource/statement target kinds, full match/context
pagination, and each fail-closed condition. Only an independent P2a PASS unlocks fresh `t`.

For `t`, order is: immutable v2 candidate with every citation -> Protocol dry-run/receipts -> actual
Evidence bindings -> apply/read/complete pagination -> independent verifier -> complete C→B→A -> all
three Agents completed and settled -> normal cleanup/evidence freeze -> independent Phase A ->
deterministic handoff -> same tester fresh-session Phase B -> final PASS. `s` remains retained BLOCKED;
there is no recovery, post-hoc evidence addition, or retry path.

### Round 60 design amendment — deterministic evidence resolution and unambiguous v2 proof

Round60 supersedes the Round59 v2 field details below where they differ. It closes the plan-review
High findings without expanding into a backend evidence product, backfill, Judge, Consumer, mutation,
recovery, UI, new table, or query-algorithm rewrite. No implementation or runtime activity is
authorized by this document.

#### Evidence resolver transaction boundary

Protocol is the only caller of a deterministic `resolve_required_evidence` helper. Its input is the
candidate citation plus frozen `project_id`, `authorization_id`, and `release_id`; it has no generic
filesystem API. For a source citation it resolves only a staged immutable source-manifest entry and
returns exactly `document_name, exact_excerpt, source_locator, artifact_sha256, excerpt_sha256`. For
an owner-answer citation it resolves only an immutable `outer-user` record selected by
`owner_answer_id` and the same authorization/release binding, hashes its exact stored text, and returns
the same five fields. Hash mismatch, unknown locator, missing staged-manifest member, wrong
project/authorization/release/permission, unreleased answer, or ambiguous result is fatal.

The helper's EvidenceReference idempotency identity is
`(project_id, source_artifact_sha256, source_locator, excerpt_sha256)`. The same citation may reuse
that one reference only inside the same frozen project/authorization/release boundary. Each use still
creates its own association binding: pre-apply target is exactly `(assertion_id, client_item_id)`;
post-apply target additionally has the calculated `fact_id`. Protocol first resolves the complete
candidate and dry-runs/creates every required EvidenceReference/association payload. Only after all
48 required citations succeed as one transactional precondition may it submit any modeling Batch.
Duplicate identity retries are idempotent; a duplicate association key, partial transaction, or any
creation/dry-run failure invalidates the whole candidate and no partial apply is allowed.

#### Evidence cardinality and exact digests

The canonical citation JSON object has exactly `source_artifact_sha256, source_locator,
excerpt_sha256, owner_answer_id`, is encoded by UTF-8 `json.dumps(ensure_ascii=False, sort_keys=True,
separators=(",", ":"))`, and has `citation_digest=SHA-256(bytes)`. Citation lists are ordered by
`(source_artifact_sha256, source_locator, excerpt_sha256, owner_answer_id-with-null-first)`. A
candidate may retain a list digest for transport diagnostics; it never proves coverage.

`evidence_bindings` remains a sorted array, but every row (not an aggregate) has exactly
`assertion_id, citation_digest, evidence_reference_id, client_item_id, batch_id, fact_id`; its unique
key is the entire tuple. For every candidate assertion and every one of its citations, verifier
requires exactly one row with the resolver's EvidenceReference identity and the materialized fact.
Same-citation reuse across assertions therefore produces distinct rows sharing only an allowed
EvidenceReference ID. Verifier recomputes citation and binding digests across the entire candidate and
rejects duplicate, missing, substituted, unbound, cross-project, or drifted rows.

#### Multi-delta term selector and proof schema

`term_bindings` has exactly these fields:

```text
assertion_id, term_position, candidate_term, binding_kind, client_item_id, batch_id,
applied_attempt_id, quad_digest, delta_index, resource_output_iri
```

`term_position` is `subject|predicate|object`; `binding_kind` is exactly
`literal_delta|resource_output|relation_delta|vocabulary`. `quad_digest` is SHA-256 of canonical
normalized-delta quad bytes; `delta_index` is a nonnegative receipt-local index, never a global
identity. For `resource_output`, output IRI is nonempty and equals that item/Batch/Attempt receipt;
for all other kinds it is null. For resource/relation/literal rows the tuple
`client_item_id, batch_id, applied_attempt_id, quad_digest` must select exactly one applied delta;
zero/multiple selection fails. `vocabulary` must instead match the frozen RDF/XSD term table.

The materializer maps every assertion position through an appropriate binding. It excludes
create-entity system quads, and selects a candidate literal only from exactly one canonical semantic
match in the applied normalized delta. Plain literal versus `xsd:string` uses the Round59 RDF1.1
semantic comparison only; materialized quad and fact ID keep the actual stored term. Language and
other typed literals match strictly. Relation/resource term bindings are equally receipt-bound—there
is never label or decorate inference.

Native v2 proof now has exactly fifteen top-level fields:

```text
mode, initial_modeling_context, final_modeling_context, workspace_context, batch_inventory,
batch_details, entities_read, statements_read, candidate_required_assertions, term_bindings,
materialized_quads, materialized_digest, evidence_bindings, statement_lineage, pagination
```

`term_bindings_digest` and `evidence_bindings_digest` are SHA-256 of their respective ordered rows;
the required top-level `materialized_digest` is SHA-256 of canonical
`{"candidate_digest":...,"term_bindings_digest":...,"evidence_bindings_digest":...,"materialized_quads":[ordered quads]}`.
The independent verifier derives all three from immutable candidate/receipt/delta/read results and
rejects missing, extra, FNV, label-derived, ambiguous, duplicate, or drifting input.

#### Verifiable pagination chain and C79 matrix gate

Every pagination page has exactly `stream_kind, request_fingerprint_sha256, page_index,
request_cursor, next_cursor, response_digest, root_match_ids_digest, response`. The fingerprint
canonical-binds principal, project, scope_mode, ontology_ids, queries, filters, depth, limit,
context_limit, workspace signature, and source signature. In each independent `matches` or `context`
stream, page 0 cursor is null; each later request cursor is the prior next cursor; indices are
contiguous; and only null terminates. Context root-match IDs must equal a subset of the final
de-duplicated match union. Cross-scope/stream or fingerprint/signature/cursor mismatch, duplicate
identity with unequal response content, truncated/degraded state, or blocking warning fails before
complete. A helper may independently validate signed cursor/response metadata; backend pagination
algorithm changes are not an acceptance prerequisite.

C79 becomes a mandatory, independently verified matrix gate. Freeze a SHA-256-addressed 48-row
assertion-ID/category matrix derived from the approved candidate/source contract—not a fabricated
business-answer fixture. Each row declares its source/citation requirement, evidence resolver result,
resource/relation/literal/vocabulary binding, plain/xsd:string/language/boolean category, lineage
target_kind, and match/context pagination coverage. P2a may apply only a smallest generated-IRI
representative subset in its disposable scope, but must validate all 48 matrix rows statically through
the resolver/coverage rules. Before the only fresh `t` apply, all 48 actual citations must pass the
resolver/Evidence precondition. C79 PASS is the hard gate before that one start.

### Round 61 design amendment — existing inline Evidence path and frozen matrix artifact

Round61 retains the Round60 term-selector and pagination-chain rules. It replaces only the assumption
that Protocol may resolve or pre-create Evidence through a helper/bridge. No new resolver MCP, Evidence
create/associate tool, SAFE_PROTOCOL_TOOLS entry, backend table, or cross-store transaction claim is
part of this amendment.

#### Modeling-owned citations and the existing Batch path

Every v2 item has a nonempty, explicit citation list. Each citation has exactly:

```text
document_name, excerpt, source_artifact_sha256, source_locator, excerpt_sha256, owner_answer_id
```

`owner_answer_id` is a string or JSON null. Modeling owns source/evidence and provides the exact
document/excerpt/locator; Protocol performs only deterministic canonical hash checks and maps each
citation to every `submit_modeling_batch` item that carries the assertion in
`inline.evidence=[{"document_name":...,"excerpt":...}]`. Protocol does not read or guess any source.

The existing Batch inline-evidence field is the only write path. Before the first `apply_atomic`,
`dry_run` must expose an `operation_plan.evidence` entry for every item and every citation, with no
missing, duplicate, hash/text/locator mismatch, or ambiguous mapping. `operation_plan.missing_evidence`
is a hard stop. PostgreSQL EvidenceReference, modeling-item association, lineage, and finalize are
one DB transaction during apply; an Oxigraph failure uses the existing `recovering` path and is not
described as instant cross-store zero-partial. A failed `t` is not retried.

After apply, the verifier reads `statement occurrence -> modeling_item origin -> EvidenceReference`
and fills the existing post-apply row exactly as
`assertion_id, citation_digest, evidence_reference_id, client_item_id, batch_id, fact_id`. No
candidate pre-provides `evidence_reference_id` or `fact_id`; fact IDs are generated by the platform.
Rule-only and delete-only items cannot satisfy the 48 asserted-lineage gate.

Source fidelity is an independent tester responsibility in P2a and `t` Phase A. The tester compares
candidate `document_name, excerpt, source_artifact_sha256, source_locator, excerpt_sha256` against
host-staged immutable sources and the immutable outer-user record; the isolated Protocol does not need
the manifest. Runner assigns `owner_answer_id`, writes it to outer-user, and passes it with the
delivery. The minimum immutable outer-user record is exactly
`owner_answer_id, project_id, run_id, authorization_id, release_id, question_delivery_id,
delivery_id, text, released_at`; a candidate citation must match that binding. An exact answer
delivery ID may serve as the owner-answer ID, but it remains Runner-assigned and release-bound.

#### Frozen 48-row matrix and start gate

The sole matrix artifact is
`modeling_team/references/r2-3-002-proof-v2-assertion-matrix.json`. Its exact top-level fields are:

```text
schema_version, source_run_id, source_candidate_digest, rows, matrix_digest
```

`schema_version` is `r2-3-002-proof-v2-assertion-matrix/v1`; `source_run_id` is exactly
`r23002-real-20260801s`;
`rows` sort by `assertion_id`; `matrix_digest` is SHA-256 over the complete object excluding itself,
using UTF-8 compact canonical JSON (sorted keys, no whitespace). Every row has exactly:

```text
assertion_id, subject, predicate, object, object_kind, object_datatype, object_language,
approved_citations, binding_category, literal_category, target_kind, p2a_branch_id,
match_coverage, context_coverage
```

`approved_citations` contains the six exact citation fields above, sorted and unique.
`binding_category` is `resource_output|relation_delta|literal_delta|vocabulary`;
`literal_category` is `none|plain|xsd:string|language|boolean`; `target_kind` is `resource|statement`;
`p2a_branch_id` is nonempty; match/context coverage are booleans. The row semantic fields are the
canonical rev7 assertion values from `s`; the artifact is frozen repair input, not evidence that `s`
was accepted.

Implementation generates this artifact from retained `s` rev7 handoff plus approved sources, then an
independent tester verifies every row. Modeling `t` cannot create or alter it. The exact binding field
names are `proof_matrix_path` and `proof_matrix_digest`; both enter TeamRunner baseline,
repair-authorization/reservation/start expected-digest evidence, and the `t` candidate proof's
`matrix_binding` object (which contains exactly those two fields). StartLedger rejects `t`'s semantic
start until independent P2a PASS and exact path/digest match are present.

P2a may apply only a minimal generated-IRI representative subset, but must statically validate all 48
rows and execute representative `resource_output`, `relation_delta`, `literal_delta`, `vocabulary`,
plain/xsd:string/language/boolean, inline Evidence, statement-lineage, pagination, and both target-kind
branches. It may not replace the matrix with arbitrary synthetic 48 business assertions. `t` may
restate semantics, but assertion IDs, scope, and citations must exactly match the matrix before its
first apply. Wrong path/digest/source candidate/assertion/citation, missing P2a evidence, or an
unmatched ledger gate fails closed.

### Round 62 design amendment — implementation-visible candidate map and existing ledger gate

Round62 converts the remaining plan-review concerns into a small implementation surface. Round61's
inline Evidence transaction, existing recovery, term selectors, pagination, and matrix row contract
remain active. This amendment adds no resolver/Evidence MCP bridge, no new tool or table, and does not
claim that the files/code described below already exist.

#### Candidate-local map and additive dry-run response

After receiving the attributed candidate and before the first submit, Protocol writes exactly once to
the current run's `evidence/candidate-item-evidence-map.json`. It is a run-local immutable regular file
and must reject symlink/path escape. Its exact envelope is:

```text
schema_version, run_id, candidate_digest, rows, map_digest
```

`schema_version="r2-3-002-candidate-item-evidence-map/v1"`; each row has exactly
`assertion_id, citation_digest, client_item_id, document_name, excerpt_sha256`. Rows sort and de-duplicate
by canonical `(assertion_id, citation_digest, client_item_id, document_name, excerpt_sha256)` bytes.
`map_digest` is SHA-256 of the complete compact sorted-key JSON excluding itself. Only candidate-provided
document name/hash is copied; no raw excerpt or host source is read. Path and digest enter the candidate
proof and stable baseline.

The Batch request remains unchanged: every submit item uses only existing inline
`evidence[{document_name,excerpt}]`; source hashes stay in the local map/proof. The additive backend
dry-run response (`_attempt_response` and its response schema) exposes a safe `operation_plan.evidence`
array with exactly `client_item_id, document_name, normalized_excerpt_sha256, dedupe_identity` per row.
It exposes no raw source beyond the submitted excerpt. Legacy/old attempts with no inline evidence may
omit the field or return `[]`; an R2.3 Protocol dry-run must expose it.

Protocol compares the map and dry-run plan by exact projected rows
`client_item_id,document_name,excerpt_sha256`; each appears once, `dedupe_identity` is stable for an
identity, and no missing/duplicate/extra/hash/text mismatch is tolerated. Only a complete comparison
and `operation_plan.missing_evidence` absence permit the first apply. This additive response does not
change generic apply, recovery, or existing consumer semantics.

#### Immutable outer-user answer records

The Runner-owned `outer-user.jsonl` immutable record has exactly:

```text
owner_answer_id, project_id, run_id, authorization_id, release_id, question_delivery_id,
delivery_id, text, released_at
```

`owner_answer_id` is `owner-answer-` plus SHA-256 of canonical UTF-8 JSON over `run_id, project_id,
question_delivery_id, text`. `authorization_id` is the standing owner-answer authorization constant
bound into task/profile baseline; `release_id` is the Runner delivery ID that releases the answer to
Modeling; `released_at` is Runner UTC. RuntimeDelivery, `receive_outer`, and Runner's prompt handoff
pass all IDs and exact text to Modeling. An owner citation must match its record; duplicate prompts do
not mint another ID. The independent tester recalculates the identity/hash on host and cross-checks
outer-user/transport delivery, release, project, and run. Document citations are independently checked
against host-staged immutable source files; Protocol isolation never needs a source manifest.

#### P2a pass artifact, binding propagation, and pre-start rejection

The implementation's tester-owned P2a gate file is fixed at
`workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json`, with exact envelope:

```text
schema_version, matrix_path, matrix_digest, source_run_id, p2a_run_id, verifier_complete,
evidence_hashes, tested_at
```

Its schema is `r2-3-002-proof-v2-gates/p2a-pass/v1`; `evidence_hashes` is a sorted 64-hex SHA-256
array and `tested_at` is UTC RFC3339. The pass digest is the external SHA-256 of full compact sorted-key
file bytes. It is not a new ledger event or tranche.

For fresh R2.3-002 `t`, existing `authorize_repair`, `reserve`, and `mark_semantic_start` payloads
carry an exact `gate_binding` object with only
`matrix_path, matrix_digest, p2a_pass_path, p2a_pass_digest, source_run_id`. Repair authorization
creates the first binding; reservation must be byte-equal to the prior qualifying repair binding;
`mark_semantic_start` must be byte-equal to reservation; and the semantic-start event retains that same
object. Historical old-run/P2 payloads without a binding remain compatible.

Before writing `semantic_start`, Runner reads the canonical matrix and P2a files, rejects missing or
symlink/path-escape targets, bad canonical hash/schema/source run, false `verifier_complete`, or
evidence-hash mismatch, and compares `gate_binding` against the task/profile's pre-frozen
`expected_matrix_binding` (the same five fields). Matrix/P2a files and gate-validation call sites are
stable baseline inputs. The task/profile binding exists before launch; candidate execution cannot
choose it. Candidate proof's `matrix_binding` must at least exactly match matrix path/digest. Any
mismatch fails before the ledger write. The unchanged budget is cap 18, consumed 17, remaining 1.

### Round 63 design amendment — citation groups and separated lifecycle gates

Round63 leaves Round62's inline-only write path, dry-run response, matrix artifact, and ledger binding
mechanics intact while making two boundaries explicit. It does not add a Batch request field for
locator/owner, a bridge/tool/table, or a new ledger event.

#### Candidate map group projection

The immutable run-local map remains one row per assertion/citation, now with exactly:

```text
assertion_id, citation_digest, client_item_id, document_name, excerpt_sha256,
inline_evidence_identity, citation_group_digest
```

`inline_evidence_identity` is the SHA-256 of canonical JSON
`{"document_name":<document_name>,"normalized_excerpt_sha256":<excerpt_sha256>}`. A group is the
exact triple `(assertion_id, client_item_id, inline_evidence_identity)`; its
`citation_group_digest` is SHA-256 of canonical JSON over the sorted unique citation-digest array.
Duplicate identical citation digest/identity rows fail. Different citation digests sharing document
and excerpt are retained as distinct rows in one explicit group.

The safe dry-run plan does not enumerate citation rows. It proves exactly one row for each
`(client_item_id, inline_evidence_identity, dedupe_identity)` and no extra/missing group identity.
Protocol projects the map by group, compares the projected inline identity/dedupe set exactly, and
retains citation-level coverage for post-apply verification. Each post-apply evidence binding row now
has exactly:

```text
assertion_id, citation_digest, evidence_reference_id, client_item_id, batch_id, fact_id,
inline_evidence_identity, citation_group_digest
```

The same or corresponding EvidenceReference must be used for every citation row in the group. The
verifier recomputes candidate citation set → group digest → inline plan identities → EvidenceReference
bindings and rejects omission, replacement, wrong group, wrong reference, or duplicates.

#### Mark gate versus candidate gate

The **mark-before-start gate** is deliberately narrow. Before `mark_semantic_start`, Runner verifies
only the canonical matrix artifact, independent P2a pass, task/profile `expected_matrix_binding`, and
ledger `gate_binding`. It does not require a live candidate, candidate map, or map digest. Stable
baseline includes matrix/P2a actual digests, map/proof schema, expected map/proof paths, and gate
call-sites, but never a digest for an uncreated map.

After a valid semantic-start event consumes the one remaining start, the **candidate-before-submit/apply
gate** runs when Modeling's candidate arrives. Before even the first `submit_modeling_batch` (including
dry-run), Protocol/Runner verifies candidate assertion IDs, scope, citations, and candidate
`matrix_binding` against the frozen matrix, then writes the immutable map. A mismatch fails before
submit/apply; the semantic start remains consumed and cannot be retried. The map digest enters runtime
proof/evidence. Only after the dry-run group projection matches the safe plan may the first apply occur.

#### Owner-answer production sequence

Runner first receives the question delivery. On the user answer, it creates the answer delivery ID,
uses that ID as `release_id`, and computes the existing release-independent `owner_answer_id` as
SHA-256 of canonical UTF-8
`json.dumps({"run_id":...,"project_id":...,"question_delivery_id":...,"text":...}, ensure_ascii=False,
sort_keys=True, separators=(",", ":"))`. It writes the
complete nine-field `outer-user.jsonl` record, and fsyncs it. Only then does it send
`owner_answer_id, release_id, text` to Modeling. A send failure retains the record, fails the run, and
never reuses the ID. Independent testing binds question delivery, answer delivery/release, exact text,
and outer-user record; source document fidelity remains a host-staged tester check.

### Round 70 P0 design amendment — exact-four P2a Protocol execution plan

This append-only amendment records the read-only D70-P0 design for plan review. It applies
R2.3-002 Round60's receipt-bound term selectors and pagination contract, Round61's inline Evidence
write path and minimal P2a subset, Round62's candidate-local map and public dry-run plan, and
Round63's citation-group projection and separated lifecycle gates. It does **not** edit, replace, or
reinterpret the authoritative requirement. Where the frozen requirement and current matrix/compiler
cannot be satisfied together, this amendment retains the conflict for explicit plan-review judgment
rather than treating a partial fixture as PASS.

This amendment authorizes no code change, test execution, runtime fixture, P2a pass artifact,
semantic start, retry, new tranche, backend business branch, or productization work. The proposed
implementation remains subject to mandatory plan review and the impact warnings below.

#### Round 70 failure and narrow repair layer

The independent Round70 P2a attempt proved the candidate receipt and candidate-item-evidence map:
the Protocol sent the exact four-field accepted receipt in reply to the candidate delivery, then wrote
and promoted an exact four-row assertion-to-client-item map. It created no Modeling Batch. Immediately
after the map checkpoint, the Protocol turn completed and the driver's bounded idle guard failed it in
about 1.25 seconds, before dry-run, apply, retrieval, native verification, or terminal report.

The failure is not an MCP visibility, credential, observer, service-lifecycle, or idle-guard defect.
The strongest root cause is a contradictory and incomplete post-map execution contract:

- generic Protocol instructions describe receipt/map as a handoff checkpoint followed by waiting for
  Modeling revision or Runner continuation;
- the P2a task has no Modeling Agent, Runner terminal handoff, or revision producer;
- the candidate and map freeze assertions, citations, and client item identities, but not a unique
  legal `command_kind`, payload, dependency graph, or support-resource plan;
- the task simultaneously requires the same four mapped items and exact observed Batch item set, so
  an Agent cannot safely invent extra class/property/entity support items.

The repair therefore stays in the `collaboration/routing + task-contract execution` layer: freeze one
P2a-only deterministic four-item plan, expose a restricted mechanical builder, and explicitly require
the Protocol to continue after the map. It does not alter generic TeamRunner settlement, MCP response
semantics, backend Modeling handlers, or observer ownership.

There is also one deterministic post-map defect that Round70 did not reach. The backend public
`operation_plan.evidence` row has exactly:

```text
client_item_id, document_name, normalized_excerpt_sha256, dedupe_identity
```

The current P2a observer passes that public row directly to a helper that expects exactly:

```text
client_item_id, inline_evidence_identity, dedupe_identity
```

The Protocol-side observer must first compute
`inline_evidence_identity(document_name, normalized_excerpt_sha256)` and pass only the helper's
three-field projection. This is a read-only shape adapter over an existing public receipt. It does not
change the backend schema, leak an excerpt, create Evidence, or weaken exact comparison.

#### Frozen P2a citations

The following two immutable citation objects are reused unchanged from the selected matrix rows.
`C_release` is used by `r23002-a004`, `r23002-a008`, and `r23002-a009`:

```json
{
  "document_name": "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/release-register.md",
  "excerpt": "| State | Publication status | Output |\n| --- | --- | --- |\n| Current Draft | not callable by other workflows | `quality_rating:number` |\n| Version 1 | published | `quality_score:number` |\n| Version 2 | published and marked latest | `quality_rating:number` |\n\nPublication makes a version available for Tool use. B has no separately recorded\ndeployment after Version 2 and its configuration identifies C only by workflow identity.",
  "source_artifact_sha256": "f5386a00a2a048831ce524ef605aed14c1124a6ac74fb8dc99c5b0a0f777caae",
  "source_locator": "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/release-register.md#L3-L10",
  "excerpt_sha256": "df080c94177b9024c7c51d8d42476151c69041191975eae1605178c46f5ecb5b",
  "owner_answer_id": null
}
```

`C_landscape` is used by `r23002-a001`:

```json
{
  "document_name": "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/workflow-landscape.md",
  "excerpt": "The content platform contains three independently managed workflows: C evaluates\ngenerated content, B generates content and invokes C as a published Tool before\nreturning its result, and A publishes B's result. Operational diagrams describe the\ndependency path as C -> B -> A. B identifies C by workflow identity, not release ID.\nEach workflow has a separate draft and publication lifecycle.",
  "source_artifact_sha256": "9dde79c61d9849776c9140aa5c3be02c17aea7800efa56135fb8dfaa0be7011e",
  "source_locator": "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/workflow-landscape.md#L3-L7",
  "excerpt_sha256": "e7048c2f8ca7d5b72ec7b212d9ef52bc2e9a78440714773a55963277360e6e4d",
  "owner_answer_id": null
}
```

Each candidate assertion retains exactly one of these full six-field citation objects. Each Modeling
item carries exactly the citation's `document_name` and byte-identical `excerpt` through the existing
inline Evidence request field. The builder never reads either host path or reconstructs an excerpt.

#### Exact-four candidate, map, and legal Modeling item contract

The P2a candidate has exactly four assertions and the candidate-item-evidence map is the following
bijection; no assertion may share a client item and no fifth item may appear:

| assertion ID | client item ID | representative binding category | target kind | citation |
| --- | --- | --- | --- | --- |
| `r23002-a008` | `p2a-01-literal-a008` | `literal_delta` | `statement` | `C_release` |
| `r23002-a009` | `p2a-02-resource-a009` | `resource_output` | `resource` | `C_release` |
| `r23002-a004` | `p2a-03-relation-a004` | `relation_delta` | `statement` | `C_release` |
| `r23002-a001` | `p2a-04-vocabulary-a001` | `vocabulary` | `resource` | `C_landscape` |

The generated P2a candidate is a mechanics fixture, not a restatement or quality acceptance of the
business model. It retains the selected matrix assertion IDs, binding branches, target kinds, and
citations while binding synthetic fixture terms. It must not be described as proof that the synthetic
terms themselves were asserted by the business sources. The independent 48-row static matrix check
remains the source-fidelity/category gate.

The four frozen candidate statements are:

```text
r23002-a008: p2a:generated-subject urn:p2a:publicationStatus "published"
              object_kind=literal
              object_datatype=http://www.w3.org/2001/XMLSchema#string
              object_language=null
r23002-a009: p2a:generated-subject urn:p2a:hasOutput urn:p2a:output
              object_kind=resource, datatype/language=null
r23002-a004: urn:p2a:workflow urn:p2a:hasVersion p2a:generated-subject
              object_kind=resource, datatype/language=null
r23002-a001: p2a:generated-subject
              http://www.w3.org/1999/02/22-rdf-syntax-ns#type
              urn:p2a:FixtureResource
              object_kind=resource, datatype/language=null
```

All four have `graph_role=asserted_data`. The fixture normalizes the selected matrix's lexical
`xsd:string` category to the full RDF datatype IRI because proof-v2's semantic equality contract uses
the full IRI. The stored quad remains the platform's actual plain literal and is never rewritten.

The returned Modeling items have exactly the normal `ModelingItemInput` fields. Empty/default fields
are materialized so dry-run and apply replay the same canonical objects.

##### Item 1 — literal assertion and sole generated resource

```json
{
  "client_item_id": "p2a-01-literal-a008",
  "command_kind": "create_entity",
  "payload": {
    "class_iri_or_legacy_id": "http://www.w3.org/2002/07/owl#Thing",
    "label": "P2a proof-v2 subject",
    "properties": {
      "urn:p2a:publicationStatus": "published"
    }
  },
  "depends_on": [],
  "evidence_reference_ids": [],
  "evidence": [
    {
      "document_name": "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/release-register.md",
      "excerpt": "<byte-identical C_release excerpt>"
    }
  ],
  "rationale": null,
  "competency_question_ids": []
}
```

The existing handler deterministically precomputes this item's `resource_id` and `resource_iri` from
Batch ID, Ontology ID, client item ID, and command kind. Let the formal apply receipt's resource IRI be
`E`. `create_entity` also writes NamedIndividual, class, platform ID, and label system quads. Those
system quads are retained in the actual delta but excluded from candidate selectors. The unique
candidate semantic quad is:

```text
Q008 = E urn:p2a:publicationStatus "published" G_asserted
```

##### Item 2 — resource-output branch and resource lineage target

```json
{
  "client_item_id": "p2a-02-resource-a009",
  "command_kind": "create_relation",
  "payload": {
    "source_entity_iri": {
      "item_ref": {
        "client_item_id": "p2a-01-literal-a008",
        "output": "resource_iri"
      }
    },
    "relation_type_iri": "urn:p2a:hasOutput",
    "target_entity_iri": "urn:p2a:output"
  },
  "depends_on": ["p2a-01-literal-a008"],
  "evidence_reference_ids": [],
  "evidence": [
    {
      "document_name": "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/release-register.md",
      "excerpt": "<byte-identical C_release excerpt>"
    }
  ],
  "rationale": null,
  "competency_question_ids": []
}
```

The handler resolves the item reference to `E`, adds the same dependency implicitly, and compiles
exactly:

```text
Q009 = E urn:p2a:hasOutput urn:p2a:output G_asserted
```

##### Item 3 — relation-delta branch and statement lineage target

```json
{
  "client_item_id": "p2a-03-relation-a004",
  "command_kind": "create_relation",
  "payload": {
    "source_entity_iri": "urn:p2a:workflow",
    "relation_type_iri": "urn:p2a:hasVersion",
    "target_entity_iri": {
      "item_ref": {
        "client_item_id": "p2a-01-literal-a008",
        "output": "resource_iri"
      }
    }
  },
  "depends_on": ["p2a-01-literal-a008"],
  "evidence_reference_ids": [],
  "evidence": [
    {
      "document_name": "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/release-register.md",
      "excerpt": "<byte-identical C_release excerpt>"
    }
  ],
  "rationale": null,
  "competency_question_ids": []
}
```

The compiled quad is:

```text
Q004 = urn:p2a:workflow urn:p2a:hasVersion E G_asserted
```

##### Item 4 — fixed RDF vocabulary branch and second resource lineage target

```json
{
  "client_item_id": "p2a-04-vocabulary-a001",
  "command_kind": "create_relation",
  "payload": {
    "source_entity_iri": {
      "item_ref": {
        "client_item_id": "p2a-01-literal-a008",
        "output": "resource_iri"
      }
    },
    "relation_type_iri": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
    "target_entity_iri": "urn:p2a:FixtureResource"
  },
  "depends_on": ["p2a-01-literal-a008"],
  "evidence_reference_ids": [],
  "evidence": [
    {
      "document_name": "docs/evaluation-scenarios/ontology-modeling-team-l3/agent-input/sources/workflow-landscape.md",
      "excerpt": "<byte-identical C_landscape excerpt>"
    }
  ],
  "rationale": null,
  "competency_question_ids": []
}
```

The compiled quad is:

```text
Q001 = E rdf:type urn:p2a:FixtureResource G_asserted
```

`urn:p2a:FixtureResource` is deliberately distinct from the Item 1 `owl:Thing` class, so the
candidate quad cannot collide with a generated class system quad. No class, property, relation-type,
or output support item is required. Absolute RDF terms are ontology data, not promoted platform
concepts; no production route, schema, handler, or sorting rule receives P2a/Workflow semantics.

#### Dry-run plan projection and exact Evidence gate

Define:

```text
I_release   = inline_evidence_identity(C_release.document_name, C_release.excerpt_sha256)
I_landscape = inline_evidence_identity(C_landscape.document_name, C_landscape.excerpt_sha256)
R_release   = runtime EvidenceReference ID deduped for C_release in this Project
R_landscape = runtime EvidenceReference ID deduped for C_landscape in this Project
```

The authoritative public dry-run operation plan must contain exactly these four item-group rows after
the Protocol-side field projection:

| client item ID | public document/hash | projected inline identity | dedupe identity |
| --- | --- | --- | --- |
| `p2a-01-literal-a008` | release-register / `df080c...` | `I_release` | `R_release` |
| `p2a-02-resource-a009` | release-register / `df080c...` | `I_release` | `R_release` |
| `p2a-03-relation-a004` | release-register / `df080c...` | `I_release` | `R_release` |
| `p2a-04-vocabulary-a001` | workflow-landscape / `e7048...` | `I_landscape` | `R_landscape` |

The first three rows may reuse the same platform EvidenceReference because the Project, normalized
document name, and normalized excerpt are identical. They may not collapse into one operation-plan
row: the map/projection key also contains `client_item_id`. The fourth row has a distinct identity.

Before apply, the Protocol independently requires all of the following:

- the persisted Batch item-ID set is exactly the four mapped IDs;
- a validated dry-run attempt exists for that Batch;
- findings contain no `missing_evidence` and no other blocking error;
- the four public plan rows project to exactly the four `(client_item_id, inline identity, dedupe)`
  groups, with no missing, duplicate, extra, or hash drift;
- no raw excerpt, locator, owner record, or authorization secret appears in the public plan;
- the exact builder-returned `items` object is retained unchanged for `apply_atomic`.

#### Applied term bindings, materialized quads, and post-apply proof

Let `B` be the formal Batch ID, `A` the successful applied attempt ID, `E` the Item 1 receipt
`resource_iri`, `H(Q)` a canonical normalized-delta quad digest, `idx(Q)` its real delta index, and
`Fxxx` the fact ID independently read for that materialized statement. Every term binding has the
Round60 exact field set:

```text
assertion_id, term_position, candidate_term, binding_kind, client_item_id, batch_id,
applied_attempt_id, quad_digest, delta_index, resource_output_iri
```

The exact binding plan is:

| assertion | subject | predicate | object | final lineage target |
| --- | --- | --- | --- | --- |
| `r23002-a008` | `resource_output(item01,B,E)` | `literal_delta(item01,B,A,H(Q008),idx)` | same `Q008` literal selector | `statement/F008` |
| `r23002-a009` | `resource_output(item01,B,E)` | `relation_delta(item02,B,A,H(Q009),idx)` | same `Q009` selector | `resource/E` |
| `r23002-a004` | `relation_delta(item03,B,A,H(Q004),idx)` | same `Q004` selector | same `Q004` selector | `statement/F004` |
| `r23002-a001` | `resource_output(item01,B,E)` | fixed `vocabulary(rdf:type)` | `relation_delta(item04,B,A,H(Q001),idx)` | `resource/E` |

For every `resource_output` binding, `resource_output_iri=E` and the selected
`client_item_id+batch_id` must expose exactly that formal receipt output. For literal, relation, and
vocabulary bindings, `resource_output_iri` is JSON null. Literal/relation selectors must uniquely
resolve by `B+A+H(Q)+idx(Q)`; a missing or ambiguous match fails. The vocabulary row uses the fixed
full RDF type IRI and still records the corresponding Item 4 receipt/delta coordinates for traceability.

The proof contains exactly four candidate materialized quads, `Q001/Q004/Q008/Q009`, with their
actual stored RDF terms and asserted graph IRI. Item 1's other generated system quads remain in the
formal applied delta but cannot enter the candidate materialized set or satisfy a candidate selector.
The proof's `materialized_digest` is independently recomputed from the candidate digest, ordered term
binding digest, ordered evidence binding digest, and four ordered materialized quads.

Every assertion has one post-apply Evidence binding row with exactly:

```text
assertion_id, citation_digest, evidence_reference_id, client_item_id, batch_id, fact_id,
inline_evidence_identity, citation_group_digest
```

The first three rows may contain the same `R_release`, but remain one row per assertion/citation with
their distinct client item and fact IDs. The fourth uses `R_landscape`. Formal readback must prove each
statement occurrence's Modeling item origin and associated EvidenceReference. Statement targets use
`target_id == fact_id`; resource targets use exactly `E` and must not be inferred from decoration.

The native proof remains the frozen 15-field v2 envelope. The Protocol, not the builder or driver,
reads and binds initial/final modeling context, workspace, Batch inventory/details, entities,
statements, receipts/deltas, Evidence, lineage, validation, reasoning, and pagination. A textual Agent
claim or driver observation cannot replace any formal receipt/read.

#### Generic match/context pagination fixture

The Protocol uses the existing generic semantic query surface with fixture terms and deliberately
small `limit=1` and `context_limit=1` values so the retained evidence exercises multiple pages. It
does not add a domain-specific P2a query, route, read model, field, or sorting rule.

Match and context are independent streams. For each stream the Protocol must retain every page with
the exact proof-v2 pagination fields, require a null first request cursor, a continuous
`request_cursor == previous.next_cursor` chain, consecutive page indices, stable request fingerprint,
scope/workspace/source signatures, and `next_cursor=null` only at the terminal page. The final context
root IDs are bound to the complete deduplicated match union. Any missing/repeated page, cross-stream
cursor, fingerprint/signature drift, `truncated`, `degraded`, blocking warning, or unconsumed cursor
prevents verifier completion.

#### Restricted `build_p2a_batch_plan` boundary

The only new deterministic mechanics operation is:

```text
build_p2a_batch_plan(
  candidate,
  candidate_item_evidence_map,
  candidate_receipt
) -> {"items": [exactly four ModelingItemInput objects]}
```

Its top-level result contains only `items`. Its arguments contain no Project, Ontology, Build Session,
workspace version, lease, API credential, Batch ID, operation mode, query, pagination, run path, or
report destination. The function:

1. deep-copies and validates candidate v2 exact fields, canonical order, citation hashes, semantic
   digest, candidate digest, frozen P2a revision, four assertion IDs, fixture terms, datatypes, target
   branches, and exact citations;
2. validates the map's schema, runtime run ID, candidate/map digests, exact assertion-to-client-item
   bijection, exact four client IDs, citation digests, inline identities, and citation-group digests;
3. requires the receipt object to have exactly `status, candidate_revision, semantic_digest,
   candidate_digest`, with `status=accepted` and all candidate bindings byte-equivalent to the output
   of the existing candidate-receipt builder;
4. deterministically returns the four frozen legal command objects above, in the frozen topological
   order, copying inline `document_name/excerpt` only from the matching candidate citation;
5. performs no source read, source choice, semantic interpretation, platform context construction,
   ID/lease allocation, write, submit, apply, retrieval, verification, artifact publication, transport,
   retry, repair, or report;
6. rejects any missing/extra/reordered fixture assertion, receipt/map drift, non-bijection, changed
   client ID, unsupported citation, extra item, or payload alternative before any platform submit.

The builder is a P2a frozen-fixture projection, not a general Modeling planner or Modeling Agent. The
staged mechanics contract currently forbids general `modeling_item_synthesis`; implementation must
record this exact task-scoped exception explicitly and continue to forbid unbounded or semantic item
synthesis. It must not silently broaden the general Protocol helper contract.

#### Task-scoped Protocol instruction override

The following text is frozen for `task_id=p2a-protocol-production` only and overrides only conflicting
generic instructions about waiting after receipt/map:

> Candidate receipt and candidate-item-evidence map are nonterminal checkpoints in this P2a task.
> P2a has no Modeling revision producer, Runner terminal handoff, or peer continuation. After sending
> the one exact receipt and writing the exact map, immediately call
> `build_p2a_batch_plan(candidate, candidate_item_evidence_map, candidate_receipt)` exactly once. Do
> not wait or become idle after map promotion. If the builder succeeds, the Protocol personally
> supplies Project/Ontology/Build Session/workspace/lease/idempotency context and executes the ordered
> Build Session lifecycle, one exact dry-run, public Evidence-plan projection and comparison,
> `apply_atomic` with the same item objects, formal receipt/delta/resource/statement/Evidence/lineage
> readback, validation/reasoning, every independent match/context cursor page, the exact 15-field v2
> proof, native verification, and one terminal report. Never pass platform context to the builder,
> never add or alter an item, never wait for Runner, and never report before the native verifier returns
> `complete=true`. A builder or platform conflict is a terminal fail-closed result, not authorization
> to synthesize a repair or retry semantic modeling.

All other Protocol isolation, source, canonicalization, receipt, Evidence, retrieval, verifier, and
reporting rules remain unchanged.

#### Literal requirement conflict retained for plan review

The exact-four item plan can cover all four binding categories and both target kinds. It cannot
truthfully make one real apply cover all of `plain, xsd:string, language, boolean`:

- the frozen current matrix contains only `literal_category` values represented by null,
  `xsd:string`, and boolean datatypes; every `object_language` is null;
- the current compiler emits a plain RDF literal for strings and typed boolean/integer/decimal for
  primitive JSON values, but exposes no Modeling payload for a language-tagged literal;
- the map requires a bijection between candidate assertions and client item IDs;
- one assertion has one object literal category, while four distinct assertions are already required
  to represent the four mutually exclusive binding categories.

Therefore an exact-four live fixture cannot prove four live literal categories. Even increasing the
item count cannot produce a live language literal with the current command inventory. This amendment
does not redefine R2.3-002 Round61's text and does not mark the unmet branch complete.

The proposed **current minimal scope** is:

- one exact-four real generated-resource apply proving `resource_output`, `relation_delta`,
  `literal_delta`, `vocabulary`, both target kinds, inline Evidence, public dry-run projection,
  post-apply Evidence/lineage, materialized proof, and independent pagination;
- live proof that the candidate's full XSD string datatype is semantically equal to the actual stored
  RDF plain literal while the materialized quad/fact ID retain the actual plain term;
- static/unit verification of boolean exactness and language equality/drift fail-closed behavior;
- static validation of all actual matrix rows and an explicit unsupported-live-language result;
- no claim that static language branches constitute a real language-literal apply PASS.

The proposed **future productization** scope, excluded from D70, is a generic platform capability for
explicit RDF literal datatype/language input, followed by a larger candidate-bearing fixture if the
authoritative requirement continues to require all four literal categories live. With mutually
exclusive representative categories, a straightforward full live fixture needs at least seven
candidate-bearing assertions/items: one each for the nonliteral binding categories plus four literal
categories. It must remain generic RDF capability, never a Dify/P2a/Workflow-specific branch.

Plan review must choose one of two honest outcomes: accept the current minimal live/static split and
record the requirement gap for later authoritative amendment, or reject exact-four completion until
the requirement owner authorizes the generic literal capability and expanded fixture. This design
document alone cannot make that requirement decision.

#### Proposed implementation surface and pre-edit impact warning

No implementation has occurred. The narrow proposed surface is:

- `modeling_team/protocol_mechanics.py`: add the restricted pure builder and an explicit frozen-P2a
  exception in the mechanics contract;
- `modeling_team/protocol_retrieval_mcp.py`: add exact MCP schema/list/dispatch for the builder;
- `modeling_team/p2a_protocol_driver.py`: freeze the candidate terms/map IDs, add the task-scoped
  instruction, observe the real public dry-run projection, and retain the exact plan evidence;
- `modeling_team/references/p2a-protocol-driver-contract.json`: bind the new tool and task contract;
- `modeling_team/runtimes/codex.py`: update the exact expected v2 Protocol MCP surface;
- `modeling_team/runner.py`: update the retained v2 baseline/runtime contract only if the mechanics
  tool remains globally advertised to all schema-v2 Protocol runtimes;
- focused Modeling Team tests only; no backend/frontend source, migration, API schema, requirement,
  test-plan, or delivery-record change is part of this amendment.

Mandatory GitNexus upstream impact analysis produced two **CRITICAL** warnings that must be accepted
by the plan reviewer before any edit:

- `TeamRunner._baseline_manifest`: 2 direct and 453 total indexed dependents; the direct callers are
  `prepare` and `preview_baseline`, with broad retained baseline/test propagation;
- `protocol_mechanics_contract`: 206 direct and 248 total indexed dependents. The index appears to
  contain over-broad relationships, but that uncertainty does not justify downgrading CRITICAL risk.

`CodexRuntimeAdapter._require_expected_mcp_servers` is LOW risk with 1 direct and 2 total dependents.
The new builder, MCP dispatch, and current unindexed P2a driver functions have UNKNOWN rather than LOW
risk. If implementation is authorized, the developer must repeat impact analysis on the final indexed
symbols, warn before any HIGH/CRITICAL change, and run `detect_changes` against `main` before commit.

#### Implementation and independent test checklist

Implementation is not complete until all of the following are satisfied:

1. freeze the four candidate statements, full-XSD-string normalization, client item IDs, command
   payloads, dependency/item-ref graph, exact citations, and canonical digests;
2. implement the pure builder with an exact three-argument schema and `items`-only result;
3. reject candidate, map, receipt, assertion, client ID, citation, digest, order, dependency, payload,
   and cardinality drift before any Batch submit;
4. expose and baseline the tool without weakening per-role MCP isolation or changing other v2 tool
   semantics;
5. apply the P2a-only instruction override and statically prove that no wait/Runner handoff remains
   after map promotion;
6. project real backend public Evidence-plan fields to inline identity before group comparison;
7. preserve the exact builder-returned items between dry-run and apply, with no hidden support item;
8. verify one Batch contains exactly four persisted item IDs and a validated dry-run contains exactly
   four safe Evidence groups with no `missing_evidence`;
9. verify Item 1's deterministic output and all three item references resolve to the same receipt IRI;
10. verify the four candidate quads uniquely select from the applied delta while create-entity system
    quads remain excluded;
11. verify exact resource-output/relation/literal/vocabulary term bindings, actual fact IDs,
    materialized digest, citation-level Evidence bindings, and resource/statement lineage;
12. force and consume multiple independent match/context pages and cover cursor, fingerprint,
    signature, truncated, degraded, warning, duplicate, missing, and cross-stream negatives;
13. prove live plain/full-XSD-string equivalence, static boolean/language success/failure branches, and
    ensure unsupported live language can never be reported as complete;
14. test MCP list/call exactness, invalid/error envelopes, runtime expected-tool isolation, P2a contract
    digests, baseline preview/prepare propagation, and retained proof-v2 runtime assets;
15. run focused P2a/protocol mechanics/MCP/Codex isolation tests, the complete Modeling Team suite,
    repository whitespace checks, and GitNexus `detect_changes(compare main)` before commit;
16. independently inspect formal raw receipts, batch details, Evidence associations, lineage reads,
    pagination pages, verifier event, cleanup, and absence of a semantic-start/PASS artifact before
    accepting the real fixture.

This checklist is prospective. No test, runtime command, fixture, service restart, code edit, or
semantic attempt was executed while writing this amendment.

#### 2026-08-02 user decision — literal live scope resolved

The user resolved the preceding literal conflict on 2026-08-02. The earlier “retained for plan
review” subsection remains historical diagnosis, but it is no longer a BLOCKED decision. The
authoritative ruling is recorded in R2.3-002 Round71 and supersedes only the conflicting P2a live
literal-coverage language from Rounds59–61.

The D70 current minimal fixture remains exact-four and `1 create_entity + 3 create_relation`. Its live
completion claim is now strictly:

- one actually stored RDF 1.1 plain literal selected from the applied delta and preserved unchanged in
  the materialized quad, statement read, fact ID, Evidence binding, and lineage;
- all four `resource_output, relation_delta, literal_delta, vocabulary` binding kinds;
- both `resource` and `statement` lineage targets;
- exact inline Evidence, safe dry-run Evidence projection, post-apply Evidence/lineage, validation/
  reasoning, and complete independent match/context pagination chains;
- RDF 1.1 plain/full-XSD-string **proof normalization only**: the candidate may carry the full
  `http://www.w3.org/2001/XMLSchema#string` comparison datatype, while the formal receipt/delta/read
  must continue to prove that the platform actually wrote a plain literal.

The fixture must not claim a typed write from the candidate datatype or semantic comparison. No
explicit `xsd:string`, boolean, integer, decimal, other datatype, or language-tagged literal is a live
P2a completion requirement. Existing boolean/typed/language static unit branches may remain as
strict-equality and fail-closed checks, but they are not Batch write/read/lineage evidence and must not
be reported as live completion.

The future generic gap is now owned by `R2.4-001` in
`docs/requirements/requirements-v2.4.md`: a business-neutral Modeling Batch RDF literal envelope with
`value` plus mutually exclusive `datatype/language`, consistent handler/compiler/API validation,
formal round-trip/read/fact identity/Evidence/lineage, and independent live acceptance. R2.4-001 is
future productization and is not a D70 implementation surface or an R2.3-002/P2a/fresh-`t` prerequisite.

Accordingly, the D70 implementation checklist must interpret its literal item as an actual plain
write plus proof normalization, retain static typed/language branches only as non-live regression
coverage, and make no backend literal-envelope change. Plan review should now evaluate whether the
exact-four mechanics faithfully implement this decided scope; it no longer needs to choose between
the two literal-scope alternatives described in the historical subsection.

### Round 70 Plan Review HIGH closure — authoritative Evidence projection and P2a-only overlay

This append closes the two remaining Plan Review HIGH findings without changing backend code or any
normal Protocol/TeamRunner contract.

#### A. Authoritative dry-run Evidence projection and stable dedupe authority

The expected projection is derived only from the fully validated candidate and its validated
candidate-item-evidence map. For each citation, mechanics recomputes the normalized excerpt SHA-256
from the candidate's exact excerpt, computes
`inline_evidence_identity(document_name, normalized_excerpt_sha256)`, and requires the map's
document/hash/inline identity and citation group to match. Expected comparison keys are the exact set
of `(client_item_id, inline_evidence_identity)` groups; the set of client item IDs must equal the
four mapped IDs exactly.

Each authoritative public dry-run row must have exactly
`client_item_id, document_name, normalized_excerpt_sha256, dedupe_identity`. Mechanics converts it to
exactly `client_item_id, inline_evidence_identity, dedupe_identity`, sorts expected and actual rows by
canonical JSON bytes, and compares them order-independently. Every expected `(client_item_id,
inline_evidence_identity)` occurs exactly once, with no missing, extra, or duplicate group.

Across the complete plan, dedupe stability is globally bijective within the P2a Project/run:

- one `inline_evidence_identity` maps to exactly one `dedupe_identity`, including when the same source
  group is reused by several client items;
- one `dedupe_identity` maps to exactly one `inline_evidence_identity`, so distinct source identities
  cannot be incorrectly merged;
- the three release-register items therefore reuse one identity/reference, while the distinct
  workflow-landscape identity/reference remains separate.

Authority and temporal stability require the original authorized dry-run submit receipt plus two
authorized `get_modeling_batch(B)` detail reads. All three observations must identify the same Batch,
same validated dry-run attempt, exact four-item set, and byte-equivalent canonical Evidence projection.
The second detail read occurs immediately before apply. The independent Host observer may repeat the
same scoped authorized detail read, but cannot replace either formal Protocol read. After apply, every
post-apply Evidence binding and EvidenceReference/lineage read must use the same `dedupe_identity`
observed pre-apply for its `(client_item_id, inline identity)` group.

Any invalid public field set, bad normalized hash, map/citation mismatch, wrong client set, duplicate,
missing or extra group, identity-to-reference drift, reference-to-identity merge, changed Batch/attempt,
different projection between reads, post-apply reference mismatch, incomplete authorized response, or
Agent-authored/cached substitute fails before apply or native verifier completion. The implementation
is a Protocol/P2a projection over the existing public rows; backend schema and behavior remain unchanged.

#### B. Isolated P2a overlay MCP and immutable capability binding

The planner is a pure function in a P2a-only mechanics module. A separate stdio MCP server
`p2a_protocol_overlay` imports that function and the Evidence projection function; it does not copy
their logic. Its exact tool surface is only:

```text
build_p2a_batch_plan
verify_p2a_dry_run_evidence_projection
```

The existing `protocol_mechanics` server remains byte-unchanged and continues to own and expose only
`build_candidate_receipt`, `write_candidate_item_evidence_map`, and
`verify_scoped_retrieval_fallback`. P2a routes receipt/map/verifier calls to that existing server and
routes only plan/projection calls to the overlay. Normal Protocol `tools/list`,
`TeamRunner._baseline_manifest`, `protocol_retrieval_mcp.py`, and the global
`protocol_mechanics_contract` remain byte-unchanged.

Only `p2a_protocol_driver` may inject the overlay. Before Runtime start it stages an independent,
read-only overlay server, pure mechanics module, and `p2a-overlay-contract.json`. The canonical
contract binds exact `task_id=p2a-protocol-production`, current `run_id`, server/tool names, frozen
planner version, asset SHA-256 values, P2a driver-contract digest, and its own digest. A P2a-only Codex
adapter subclass mounts the already-open immutable asset descriptors and appends the extra MCP server
configuration; the normal Codex adapter is not modified. Its MCP preflight requires the three normal
servers with their unchanged tools plus the one exact overlay server.

The Host validates task ID, run ID, contract digest, asset digests, ownership, regular-file/no-symlink
status and read-only modes before process start. The overlay server independently revalidates the same
environment and mounted contract before advertising tools and on every call; the candidate map run ID
must equal the bound runtime run ID. A non-P2a task, absent overlay binding, missing asset, extra tool,
task/run/digest mismatch, tamper, symlink/path replacement, cross-run map/receipt, or direct launch
without the exact staged contract fails before the first Protocol turn or before returning items.

#### Revised impact, tests, and implementation order

The earlier proposed edits to `TeamRunner._baseline_manifest` and `protocol_mechanics_contract` are
withdrawn. Their two CRITICAL impact warnings remain historical evidence but neither symbol is modified.
The normal `CodexRuntimeAdapter._require_expected_mcp_servers` and global MCP wrapper are also unchanged.
Proposed existing P2a driver symbols (`_stage_run`, `_task_text`,
`_observe_authoritative_dry_run`, `run_driver`) are currently unindexed and therefore UNKNOWN risk;
the pure planner, projection helper, overlay server, overlay contract and P2a-only adapter are new and
also UNKNOWN until indexed. Final implementation still requires fresh impact analysis and
`detect_changes(compare main)` before commit.

Focused tests must cover exact/order-independent projection, four-client coverage, same-source reuse,
different-identity separation, both directions of dedupe bijection, duplicate/missing/extra rows,
receipt/detail read drift, unauthorized/incomplete reads, and post-apply EvidenceReference mismatch.
Overlay tests must prove exact two-tool exposure, reuse of unchanged receipt/map/verifier routing,
normal Protocol absence, unchanged global tool list/baseline/mechanics bytes, exact immutable staging,
task/run/digest/tamper/cross-run failures, descriptor cleanup, and no first turn on failed preflight.
The real P2a acceptance must inspect both formal detail reads, the independent observer read, apply
bindings/lineage, cleanup, and absence of semantic-start/PASS publication.

Implementation order is fixed: (1) pure planner and projection functions with negative unit tests;
(2) one-tool-family overlay wrapper and immutable contract validation; (3) P2a-only adapter subclass
and descriptor staging; (4) P2a driver task/contract/observer integration; (5) focused isolation and
projection tests; (6) full Modeling Team regression plus GitNexus change detection; and only after a
reviewed stable state, (7) one independent real P2a run. No backend, requirement, test-plan,
delivery-record, global MCP contract, or TeamRunner baseline change belongs to this closure.

### D74-P2A-01 design amendment — deterministic native-proof construction

This append-only amendment responds only to the independent Round74 failure and the subsequent
D74-P2A-01 diagnosis. Round74 proved candidate receipt/map, the exact-four plan, authoritative
dry-run, apply, four post-apply Evidence bindings, two retrieval episodes through complete, cleanup,
and safe failure classification. The native verifier then returned `error_code=-32010` with
`failure_layer=proof_validation` while `top_level_exact`, `types_valid`, and `mode_create` were all
true. The retained message hash cannot identify a nested field, and the safe evidence contract must
not be weakened to recover raw arguments or error text.

The remaining design defect is therefore deterministic construction ownership. The passing pure
exact-four fixture mechanically creates twelve term bindings, four materialized quads and fact IDs,
four Evidence bindings, four lineage records, canonical digests, and two complete pagination streams.
The production Protocol is currently asked to hand-construct those structures from prose. This
amendment moves only that formatting, selector, identity, and hashing work into a P2a-only pure
builder. It does not change the semantic candidate, platform lifecycle, native verifier contract,
retrieval gate, or terminal-report authority.

This amendment authorizes no implementation, test execution, real P2a run, semantic start, `t`, gate
publication, ledger mutation, retry, backend/frontend change, requirement change, test-plan update,
delivery-record update, or productization work. Implementation still requires plan review and the
ordered checks defined below.

#### Frozen responsibility and call sequence

The only allowed sequence is:

```text
Protocol collects formal platform inputs and all pages
  -> p2a_protocol_overlay.build_p2a_native_proof
  -> Protocol passes returned structuredContent unchanged to
     protocol_mechanics.verify_scoped_retrieval_fallback
  -> native verifier returns complete=true
  -> Protocol personally calls report_task_result
  -> driver observes terminal state and performs cleanup
```

Ownership is fixed:

- **Protocol** chooses and executes the already-frozen platform reads, retains every unmodified formal
  envelope and request/response page, calls the builder, calls the existing native verifier with the
  builder result as the direct arguments, evaluates `complete=true`, and sends its own correlated
  Broker terminal report.
- **The builder** validates formal inputs and derives only deterministic proof structure. It has no
  network client, credentials, filesystem writer, Runtime reference, Broker reference, gate path,
  driver callback, or verifier callback.
- **`verify_proof_v2`** remains the independent acceptance authority. The builder must not import or
  call `verify_proof_v2`, catch its error, synthesize its completion, or share mutable state with it.
- **The P2a driver** may change only its task text and safe observation/cleanup integration. It does
  not collect missing proof fields, repair builder output, call the verifier, report for Protocol, or
  infer PASS.
- **The Host/P2a adapter** stages and authorizes the exact overlay capability. It never sees or
  retains raw proof arguments or results outside the existing app-server transport.

The normal Codex adapter, normal three-server surface, global `protocol_mechanics` server,
`protocol_retrieval_mcp.py`, `TeamRunner`, baseline contract, backend, and `verify_proof_v2` remain
byte-unchanged.

#### Independent pure module and exact function contract

Add one task-specific module, proposed as `modeling_team/p2a_native_proof.py`, containing:

```text
build_p2a_native_proof(
  scope_metadata,
  candidate,
  candidate_item_evidence_map,
  candidate_receipt,
  initial_modeling_context,
  final_modeling_context,
  workspace_context,
  batch_inventory,
  dry_run_receipt,
  detail_read_1,
  detail_read_2,
  apply_receipt,
  applied_detail,
  entities_read,
  statements_read,
  lineage_reads,
  evidence_reads,
  postapply_evidence_bindings,
  match_page_records,
  context_page_records
) -> exact fifteen-field proof-v2 object
```

The MCP argument object has exactly those twenty fields, all required, with
`additionalProperties=false`. There is no optional compatibility wrapper and no nested `proof`
argument. The pure Python function receives the same values as keyword-only or positional arguments
but normalizes neither missing nor extra fields.

The fixed top-level types are:

| field | exact outer type and authority |
| --- | --- |
| `scope_metadata` | exact object defined below; Protocol supplies Host-visible public identity only |
| `candidate` | complete immutable `candidate-required-assertions/v2` object |
| `candidate_item_evidence_map` | complete run-bound map object, including `map_digest` |
| `candidate_receipt` | exact accepted four-field receipt returned by Protocol mechanics |
| `initial_modeling_context`, `final_modeling_context`, `workspace_context` | unmodified successful formal MCP envelopes |
| `batch_inventory` | exact request metadata plus unmodified list response, as required by proof-v2 |
| `dry_run_receipt` | unmodified R0 dry-run submit result |
| `detail_read_1`, `detail_read_2` | unmodified R1/R2 successful Batch detail envelopes |
| `apply_receipt` | unmodified successful `apply_atomic` submit result, including item results/resource outputs |
| `applied_detail` | unmodified post-apply successful Batch detail envelope, including the applied attempt and normalized delta |
| `entities_read`, `statements_read` | unmodified successful formal read envelopes/request metadata |
| `lineage_reads` | exact-four records with `assertion_id,target,response`; every `response` is unmodified formal lineage output |
| `evidence_reads` | exact-four records with `assertion_id,response`; every `response` is unmodified formal Evidence association output |
| `postapply_evidence_bindings` | exact-four safe rows already proven against dry-run identity/dedupe authority |
| `match_page_records`, `context_page_records` | nonempty arrays of exact `{request,response}` records; both members are unmodified formal values |

`scope_metadata` has exactly these fields:

```text
schema_version = "p2a-native-proof-input/v1"
task_id = "p2a-protocol-production"
run_id = current nonempty P2a runtime run ID
overlay_contract_digest = current materialized overlay contract digest
mode = "create"
project_id = current isolated P2a Project ID
ontology_id = current isolated P2a Ontology ID
default_graph_set_id = workspace default graph-set ID
source_signature = workspace source signature
asserted_data_graph_iri = workspace asserted-data graph member
candidate_batch_id = exact four-item Batch ID
dry_run_attempt_id = R0/R1/R2 validated dry-run attempt ID
applied_attempt_id = applied attempt ID
```

All twelve fields are required strings except no field permits null; their names are exact and no
credential, key, lease secret, filesystem path, raw app-server event, raw error, Broker delivery,
gate path, or terminal claim may appear. The overlay wrapper independently supplies the authorized
task/run/contract values from its immutable environment and contract and requires them to equal the
three corresponding metadata fields before calling the pure builder. The pure builder then repeats
the same exact equality checks so direct Python use cannot bypass task/run/contract binding.

`lineage_reads` rows have exactly:

```text
assertion_id, target, response
```

where `target` has exactly `target_kind,target_id`. `evidence_reads` rows have exactly
`assertion_id,response`. Page records have exactly `request,response`. These small association
wrappers identify which unmodified formal response is being bound; they may not contain copied facts,
selected labels, rewritten envelopes, cached summaries, or Agent explanations.

#### Protocol collection contract

Protocol must collect, not invent, every builder input:

| input | Protocol collection responsibility |
| --- | --- |
| initial/final modeling contexts | call the existing scoped modeling-context read before the first write and after all writes |
| workspace context | call the existing workspace-context read and retain default graph set, source signature, and exact ontology-owned graph members |
| batch inventory | execute the unfiltered inventory request with a limit larger than the returned set and require terminal `next_cursor=null` |
| R0 | retain the formal validated dry-run submit receipt |
| R1 | immediately read the same Batch after R0 |
| R2 | read the same Batch again immediately before apply |
| apply receipt | submit the exact retained four-item plan using `apply_atomic` and retain its full formal response |
| applied detail | read the same Batch after apply and retain the complete applied attempt and normalized delta |
| resource outputs | retain them only in their authoritative apply receipt/detail locations; no Agent-authored resource-output projection is accepted |
| entity/statement reads | call the existing generic scoped read tools and retain their complete successful envelopes and request metadata |
| Evidence | read the four authoritative post-apply associations and retain exact responses; the safe postbinding rows remain an independent cross-check |
| lineage | issue the required statement/resource provenance reads for all four assertions and retain exact responses |
| matches/context pages | make every continuation request independently for each stream and retain every exact request and exact successful response through terminal null |

The builder rejects a value merely copied from driver observation when the formal Protocol response is
required. The driver may observe the same state independently, but its observation is never builder
input and never substitutes for R0/R1/R2, applied detail, Evidence, lineage, statements, or pages.

#### Exact-four validation before derivation

Before constructing any output, the builder deep-copies inputs and fail-closes on all of the following:

1. task, run, contract, mode, Project, Ontology, graph-set, source-signature, asserted-data graph,
   Batch, and attempt identity drift across metadata and formal responses;
2. any missing/extra top-level or nested association-wrapper field, wrong type, unsuccessful formal
   envelope, duplicate association, or noncanonical candidate/map array;
3. candidate revision/delivery/semantic/candidate digest drift, anything other than the frozen four
   assertion IDs and terms, or any map/receipt/citation/client-ID mismatch;
4. anything other than the exact four Batch item IDs and frozen one-entity/three-relation plan;
5. R0, R1, and R2 canonical inequality. Equality is over the same validated dry-run Batch/attempt,
   item set, normalized delta, findings, and Evidence-plan projection; timestamps or wrapper fields
   not part of the formal retained response may not be silently dropped to manufacture equality;
6. apply receipt/detail disagreement, a non-applied item, more than one applied attempt, missing or
   ambiguous normalized-delta selector, or a resource output other than the sole Item-1 IRI `E`;
7. any candidate `resource` object that is not an actual materialized `iri`, or any IRI lexical-value
   mismatch. Equivalence is one-way `candidate resource -> materialized iri` only;
8. any literal except the exact `published` RDF 1.1 plain literal. Candidate full
   `http://www.w3.org/2001/XMLSchema#string` and actual null datatype are semantically equivalent only
   for this exact P2a assertion; the actual quad/read/fact construction remains plain and unchanged;
9. Evidence rows that do not form the exact assertion/citation/client/Batch/fact bijection, any
   inline-identity or citation-group digest drift, wrong same-source reference reuse, or mismatch with
   the independently supplied postbinding rows;
10. lineage response/target/evidence-reference drift. `r23002-a008` and `r23002-a004` are statement
    targets with `target_id=fact_id`; `r23002-a009` and `r23002-a001` are resource targets with
    `target_id=E`;
11. a statement read that omits a derived fact ID, an entity read that does not bind `E`, or a
    workspace/graph/source signature mismatch;
12. a page stream with a non-null first request cursor, discontinuous or reused cursor, noncontiguous
    index, changing cursor-free request basis, incomplete/degraded/truncated response, blocking warning,
    conflicting duplicate identity, context root outside the final match union, or final
    `next_cursor != null`.

The builder produces no partial output. One failed check raises a P2a-builder error that the overlay
returns as a normal MCP error; it never returns `complete`, `accepted`, a verifier result, or a
terminal category.

#### Mechanical derivation of the exact proof

Let `B` be the bound Batch ID, `A` the applied attempt ID, `E` the sole Item-1 `resource_iri`,
`G` the asserted-data graph, `Qxxx` the actual selected normalized-delta quad, `idx(Q)` its real array
index, and `H(Q)` the SHA-256 canonical digest of the unmodified normalized-delta representation. The
builder selects exactly:

```text
Q008 = E urn:p2a:publicationStatus "published" G   (actual plain literal)
Q009 = E urn:p2a:hasOutput urn:p2a:output G         (actual IRI object)
Q004 = urn:p2a:workflow urn:p2a:hasVersion E G       (actual IRI object)
Q001 = E rdf:type urn:p2a:FixtureResource G          (actual IRI object)
```

Create-entity system quads remain in the applied delta but cannot enter this four-quad set. Quads are
projected to the existing exact materialized-quad field set and sorted by canonical JSON bytes.

The exact twelve binding rows are:

| assertion | subject binding | predicate binding | object binding |
| --- | --- | --- | --- |
| `r23002-a008` | `resource_output(item01,B,E)` | `vocabulary(urn:p2a:publicationStatus)` | `literal_delta(item01,B,A,H(Q008),idx(Q008))` |
| `r23002-a009` | `resource_output(item01,B,E)` | `vocabulary(urn:p2a:hasOutput)` | `relation_delta(item02,B,A,H(Q009),idx(Q009))` |
| `r23002-a004` | `vocabulary(urn:p2a:workflow)` | `vocabulary(urn:p2a:hasVersion)` | `resource_output(item01,B,E)` |
| `r23002-a001` | `resource_output(item01,B,E)` | `vocabulary(rdf:type)` | `vocabulary(urn:p2a:FixtureResource)` |

Every row still carries the exact ten proof-v2 binding fields. Vocabulary rows carry their
assertion's real `B,A,H(Q),idx(Q)` coordinates and null `resource_output_iri`; resource-output rows
carry Item 1 and exact `E`; literal/relation selectors resolve uniquely to the named actual quad.
Rows are sorted by canonical JSON bytes only after all selectors are verified.

Fact IDs are mechanically computed from each actual RDF quad using the frozen proof-v2 canonical
statement form: delimited subject/predicate/graph IRIs; IRI objects delimited as IRIs; the actual
plain literal escaped and quoted without adding a datatype; then UTF-8 SHA-256. The computed four IDs
must equal the formal statement and lineage responses. They are never accepted from an Agent-authored
map alone.

For each assertion's sole candidate citation, the builder recomputes the six-field citation digest,
inline Evidence identity, and singleton citation-group digest; binds the map's client item, `B`, the
computed fact ID, and the authoritative EvidenceReference from the formal Evidence/lineage reads; and
requires exact equality with the supplied postbinding row. The result is exactly four canonically
sorted Evidence-binding rows.

The builder constructs exactly four lineage records by joining the computed fact/quad, the frozen
target rule above, and the corresponding unmodified formal lineage response. It does not decorate,
summarize, or reinterpret the response.

#### Pagination records and canonical fingerprints

The input arrays are already separated into `match_page_records` and `context_page_records`; the
builder does not infer a stream from result content. For each record it derives the proof page from
the unmodified request and response:

```text
stream_kind
page_index
request_cursor
next_cursor
response
response_digest = canonical_digest(response)
root_match_ids_digest = canonical_digest(sorted(unique(root_match_ids)))
request_fingerprint_sha256
```

The request fingerprint is SHA-256 of canonical JSON bytes for exactly:

```json
{
  "stream_kind": "matches|context",
  "scope": {
    "project_id": "<bound>",
    "ontology_id": "<bound>",
    "default_graph_set_id": "<bound>",
    "source_signature": "<bound>"
  },
  "request_without_cursor": "<exact request with only that stream's cursor field replaced by null>"
}
```

No other request field is removed or normalized. Thus all pages in one stream have one fingerprint,
matches and context remain independently fingerprinted, and changing a query, limit, include/filter,
scope, graph, source signature, or the other stream's request basis fails. The builder preserves every
page, enforces the complete cursor chain through final null, canonical-sorts neither page order nor
requests, and emits the two stream records in fixed `matches, context` order.

#### Canonical digest and exact output rules

All canonical bytes use UTF-8 JSON with `ensure_ascii=false`, recursively sorted object keys, and
separators `(',', ':')`. Arrays are not implicitly reordered. Only arrays explicitly declared above
as sets of independent records—term bindings, materialized quads, Evidence bindings, and lineage
records—are sorted by their full canonical bytes after duplicate rejection. Candidate/map order,
R0/R1/R2 content, normalized-delta order, statement response order, and pagination page order remain
authoritative and are never repaired by sorting.

The builder recomputes:

```text
term_bindings_digest = canonical_digest(sorted 12 binding rows)
evidence_bindings_digest = canonical_digest(sorted 4 Evidence rows)
materialized_digest = canonical_digest({
  "candidate_digest": candidate.candidate_digest,
  "term_bindings_digest": term_bindings_digest,
  "evidence_bindings_digest": evidence_bindings_digest,
  "materialized_quads": sorted four quads
})
```

It returns exactly the existing fifteen fields and no builder metadata:

```text
mode
initial_modeling_context
final_modeling_context
workspace_context
batch_inventory
batch_details
entities_read
statements_read
candidate_required_assertions
term_bindings
materialized_quads
materialized_digest
evidence_bindings
statement_lineage
pagination
```

The first eight formal proof values and candidate are deep-copied from validated inputs without
rewriting their envelopes. `batch_details` contains the validated applied detail required by the
existing verifier; R0/R1/R2 and apply receipt remain builder validation inputs rather than new proof
fields. Protocol must pass this returned `structuredContent` object unchanged as the direct argument
object to `verify_scoped_retrieval_fallback`: no `{proof: ...}` wrapper, JSON text round-trip,
field insertion/removal, Agent repair, or driver projection is permitted.

#### Overlay tool surface changes from two to three

The P2a-only overlay exact ordered tool surface changes from:

```text
build_p2a_batch_plan
verify_p2a_dry_run_evidence_projection
```

to:

```text
build_p2a_batch_plan
verify_p2a_dry_run_evidence_projection
build_p2a_native_proof
```

`p2a_protocol_overlay_mcp.py` imports the pure builder and exposes the exact twenty-field schema above
with `additionalProperties=false`. Wrong/missing/extra fields return `-32602`; task/run/contract or
proof-input validation failures return one fixed P2a builder error code, proposed `-32023`. This code
is an MCP transport classification only, not a reason enum, verifier verdict, or PASS state.

The immutable overlay contract remains `p2a-protocol-overlay-contract/v1` unless implementation review
finds a compatibility reason to version it; its content changes atomically as follows:

- `tools` becomes the exact ordered three-tool list above;
- a fourth asset binds `modeling_team/p2a_native_proof.py` to `/opt/p2a_native_proof.py` with
  `mode=0444` and its exact SHA-256;
- the overlay MCP, existing P2a planner, and `proof_v2.py` asset hashes are refreshed only when their
  bytes actually change;
- `contract_digest` is recomputed from canonical contract JSON with only `contract_digest` omitted;
- the P2a driver contract's `runtime_contract.p2a_overlay.tools` and asset/digest binding are updated
  to the same exact values.

The P2a adapter's expected tool set and preflight become exact-three. Its elicitation allowlist accepts
the Host-generated exact approval message only for one of those three names, including
`build_p2a_native_proof`, while retaining the existing exact server, schema, metadata, thread/turn,
task/run/role, preflight, immutable-path, contract, digest, ownership, and mode checks. Missing/extra
tool, fourth tool, wrong message/tool metadata, cross-run contract, stale self-digest, missing builder
asset, tamper, symlink, or non-read-only mode fails closed. Every non-overlay notification continues to
delegate to the unchanged normal adapter.

Normal/global tool lists remain unchanged. `build_p2a_native_proof` is never added to
`protocol_mechanics`, the normal Protocol profile, TeamRunner baseline, or non-P2a runtime.

#### Driver task text and terminal ownership

The P2a `_task_text` must list the collection order and exact builder call after apply, postbinding,
and complete pagination. It must state explicitly:

1. collect all twenty builder arguments from current formal calls;
2. call the P2a overlay builder exactly once for the final proof construction;
3. take `structuredContent` without editing and call the existing native verifier with those fifteen
   fields as direct arguments;
4. accept only native `complete=true`;
5. only then call `report_task_result` itself.

It must not instruct Protocol to hand-create term bindings, quads, hashes, fact IDs, Evidence bindings,
lineage wrappers, or pagination fingerprints. Existing driver observers may recognize the builder
tool's safe completion at server/action or stage level, but builder completion is not a required
terminal stage and cannot advance the native-verifier or Broker gate. Driver timeout, cleanup,
deletion, credential destruction, and no-semantic-start rules remain unchanged.

#### Negative contract cases

Pure builder tests must fail closed for at least:

- missing, extra, wrong-type, null, wrapped, or non-JSON top-level arguments;
- task/run/contract, Project/Ontology, graph-set/source-signature/graph, Batch, dry-run attempt, or
  applied-attempt drift;
- candidate/map/receipt/citation/client-ID/order/digest drift or any non-exact-four cardinality;
- R0/R1/R2 inequality, incomplete dry-run, Evidence-plan drift, apply receipt/detail mismatch,
  ambiguous delta, extra applied attempt, missing/extra resource output, or wrong `E`;
- candidate resource with materialized literal/resource, actual wrong IRI, reverse iri-to-resource
  coercion, or an IRI selector/value/digest/index mismatch;
- plain/full-XSD mismatch outside exact A008, typed actual literal, language tag, wrong lexical value,
  or an attempt to rewrite the actual plain quad;
- fewer/more than twelve bindings, wrong binding kind/position/client item, non-null vocabulary output,
  missing/ambiguous selector, unsorted or duplicate row;
- wrong fact canonicalization, missing statement, extra candidate quad, create-entity system quad
  selected as a candidate, or materialized digest drift;
- missing/extra/duplicate Evidence binding, citation/inline/group/reference/fact drift, broken same-source
  dedupe reuse, postbinding mismatch, or missing Evidence in lineage;
- wrong statement/resource lineage target, wrong `target_id`, response/assertion mismatch, or fewer/more
  than four lineage records;
- missing matches/context stream, non-null first cursor, skipped/reused/cross-stream/unconsumed cursor,
  noncontiguous page index, request-basis/fingerprint/response/root digest drift, conflicting duplicate,
  context root outside match union, truncated/degraded response, warning, or terminal non-null cursor;
- any builder attempt to call a client, write a file, invoke verification, emit a Broker report, write a
  gate, or return `complete`.

Overlay/adapter/driver negatives must cover exact three-tool list/order, schema extra rejection,
builder exception envelope, task/run/contract revalidation, immutable asset hash/mode/path/tamper,
approval for the new exact tool, wrong/extra tool decline, normal policy delegation, absence from normal
tools, and proof structured-content identity between builder return and verifier arguments.

#### Ownership and impact constraints

Proposed implementation ownership is non-overlapping:

- `modeling_team/p2a_native_proof.py` and its dedicated tests: pure validation and construction only;
- `modeling_team/p2a_protocol_overlay_mcp.py`, overlay contract, and overlay tests: exact third tool,
  immutable authorization, schema and error envelope;
- `modeling_team/runtimes/p2a_codex.py` and P2a runtime tests: exact-three preflight/staging/approval only;
- `modeling_team/p2a_protocol_driver.py`, its contract, and driver tests: task text plus safe observer and
  cleanup continuity only;
- `modeling_team/proof_v2.py`, normal `codex.py`, global mechanics/wrapper, runner, backend, frontend,
  requirements, test plan, and delivery record: no owner and no edit.

The current indexed impact result is frozen for planning:

- `p2a_protocol_overlay_mcp.handle`: **LOW** upstream impact;
- `p2a_protocol_driver._task_text`: **LOW** upstream impact;
- new `build_p2a_native_proof`: **UNKNOWN** until indexed, so implementation must index it and rerun
  upstream impact before editing any caller around it;
- existing `build_p2a_batch_plan`: **MEDIUM** upstream impact and explicitly not modified.

Any refreshed HIGH/CRITICAL result must be reported before implementation continues. Post-change
`detect_changes` must be interpreted against the shared dirty worktree and accompanied by owned-file
diff/digest evidence; a shared-tree aggregate is not attributed to this amendment without a matching
owned symbol/file.

#### Test plan and implementation order

Implementation order is fixed:

1. extract the current exact-four pure fixture's mechanical construction into the new pure module
   without modifying `verify_proof_v2`; make builder output byte-equal to the fixture's exact fifteen
   fields and independently pass the unchanged verifier;
2. add exact input-schema, R0/R1/R2, term/resource/literal/Evidence/lineage/fact/digest/pagination
   positives and the negative matrix above;
3. expose the exact third overlay tool, update the immutable four-asset contract and self-digest, and
   prove list/call/error/direct-launch isolation;
4. update only the P2a adapter's exact-three staging, preflight and elicitation approval; prove normal
   three-server/tool behavior and frozen global hashes remain unchanged;
5. update `_task_text` and the P2a driver contract so Protocol collects inputs, uses builder
   structured content unchanged, calls the independent verifier, and personally reports only after
   `complete=true`; driver remains observer/cleanup owner;
6. run focused builder/overlay/adapter/driver/proof tests, complete Modeling Team tests, Ruff,
   compilation, JSON/contract/self-digest checks, whitespace checks, frozen global hashes, and owned
   GitNexus impact/change detection;
7. submit the stable implementation for mandatory plan review and independent testing; only a later
   independently authorized round may perform one real P2a attempt.

No additional raw observation, error-message retention, error-hash dictionary, reason enum, MCP facade
classification, relaxed proof rule, synthetic completion, driver verifier call, or automatic report is
a prerequisite. D74 remains a proof-construction defect until the unchanged verifier independently
returns `complete=true`; builder success alone is never P2a PASS.

### Round 75 current-minimal amendment: bounded same-Protocol correction

This amendment supersedes the Round 74 builder as the current implementation path. The entire
deterministic native-proof builder proposal—including `modeling_team/p2a_native_proof.py`, the third
overlay tool, four-asset staging/approval, builder-specific task text, implementation order, and the
two builder-schema review Highs—is **future/contingent** and MUST NOT be implemented in the current
minimal round. Those two Highs are not reopened as standalone work while their builder is deferred.

The existing overlay remains an exact two-tool surface:

1. `build_p2a_batch_plan`;
2. `verify_p2a_dry_run_evidence_projection`.

The already accepted receipt and candidate/map mechanics remain in `protocol_mechanics`; the Batch
plan tool and exact-four dry-run/apply path remain unchanged. This amendment adds no tool, proof
schema, lifecycle, semantic write, or platform API. Its only current-minimal claim is that the same
Protocol Agent can read an actionable native-verifier error from its transient conversation, correct
only the proof input, and continue the same task under a hard bound.

#### Frozen counters and continuation eligibility

The driver owns two run-local counters only:

- `native_call_count`, initially `0`, counts every observed completed or failed
  `verify_scoped_retrieval_fallback` call across the original turn and the optional continuation;
  its hard maximum is `3`;
- `continuation_count`, initially `0`, counts Host continuation deliveries and has a hard maximum of
  `1`.

The Protocol Agent may correct and retry during its original running turn; every call consumes the
shared native-call budget. The Host MUST NOT interrupt, steer, or continue an Agent that is still
running. It may issue the single continuation only when all of the following predicates are true at
the same observation point:

- receipt publication has completed;
- candidate/map promotion has completed;
- dry-run has completed;
- the one authorized apply has completed;
- post-apply Evidence binding has completed;
- retrieval is complete under the existing driver contract;
- at least one native-verifier failure has been observed, its safely classified `failure_layer` is
  `argument_contract` or `proof_validation`, and `native_call_count < 3`;
- no native-verifier `complete=true` success has been observed;
- no Broker result/report has been observed or accepted;
- the Protocol Agent is naturally idle after normal turn completion, with no active turn;
- the exact existing Project, Ontology, Build Session, Lease, and credential identities still equal
  their frozen baseline identities, and the Lease and credential retain their original expiry;
- `continuation_count == 0`, the original run/scope is still live, and cleanup has not begun.

These predicates are conjunctive. Missing or ambiguous state is ineligible and fails closed. Host
configuration/approval, platform-state ambiguity, deterministic-plan failure, apply uncertainty,
transport/runtime/infrastructure failure, and every failure not safely classified as
`argument_contract` or `proof_validation` MUST NOT enter this correction path.

The authoritative identity invariant is: continuation 必须复用 exact existing
Project/Ontology/Build Session/Lease、credential identity 及其原始 expiry；严禁 acquire、renew、
extend、restore 或 recreate Lease、Session、credential。driver 必须在 `send_message` 前比较冻结
baseline identity/expiry 与当前 Runtime/平台可见状态；任一状态 invalid、missing、changed 时
continuation 不可用，必须 fail closed 并走既有清理。

This is a pre-delivery gate, not a recovery mechanism. The driver freezes the already-established
Project ID, Ontology ID, Build Session ID, Lease identity and original expiry, and credential safe
identity and original expiry before correction becomes eligible. Immediately before `send_message`,
it compares every frozen value with the currently visible Runtime/platform state. Only exact identity
and expiry equality passes. Missing, invalid, expired, replaced, restored, recreated, renewed, or
extended state makes continuation ineligible and resumes existing cleanup; the driver MUST NOT repair
or refresh it. No raw credential is retained or added to evidence.

#### Existing Adapter interface and fixed continuation

The current implementation interface is reused exactly:

```python
adapter.send_message(PROTOCOL_ID, RuntimeDelivery(...))
```

For a naturally idle Codex Agent, `CodexRuntimeAdapter.send_message` uses the existing `turn/start`
RPC with that Agent's existing `thread_id`; it does not create a new Agent or thread. The current
path MUST call this public Adapter method and MUST NOT call `_rpc` directly, rerun `start_roster` or
`start_task`, launch a process, manufacture a lifecycle event, or use `turn/steer` after natural
idle. The Agent ID, thread, run, live read-only context, Project/Ontology, and scope remain identical.

The one `RuntimeDelivery` is frozen as a Host-to-Protocol continuation, not a Broker report:

- `sender_id = "p2a-host"`;
- `recipient_id = "protocol"`;
- `kind = "p2a-native-correction"`;
- `delivery_id = f"{run_id}-native-continuation-1"`;
- `expects_reply = false` and `reply_to_delivery_id = null`;
- `text` is exactly the following paragraph, with no dynamic raw error or proof content interpolated:

> Continue the same P2a Protocol task in this same thread and run. Inspect the native-verifier tool
> error visible in the preceding turn. Correct only the proof input; if needed, perform additional
> read-only platform reads. Do not repeat dry_run or apply_atomic, submit any platform write, change
> the candidate or modeling semantics, create a Project, Ontology, or scope, or report to Team
> Transport unless the native verifier returns complete=true. The total native-verifier call budget
> across the original turn and this continuation is three.

The Host records the delivery only after `send_message` succeeds and increments
`continuation_count` exactly once. It never copies the preceding tool error into the delivery. The
continuation does not reset any stage, receipt, map, Batch plan, attempt identity, call count, timeout,
or cleanup owner.

#### Terminal behavior and no-repeat invariants

- A third failed native-verifier call terminates the run as failure; no continuation is sent if the
  third call occurred in the original turn.
- Natural idle at the end of the continuation terminates the run as failure whenever no native
  success/Broker result exists, even if fewer than three calls were consumed. A second continuation
  is forbidden.
- A continuation-delivery failure or non-correctable failure terminates fail closed and enters the
  existing cleanup path.
- `complete=true` still requires the same Protocol Agent to emit its own authorized Broker report.
  The Host neither invokes the verifier nor emits, repairs, or synthesizes a report. A premature
  Broker report remains guard-rejected and cannot become success.
- Across original and continuation turns there remains exactly one dry-run/apply chain: no repeated
  `dry_run`, `apply_atomic`, semantic revision, candidate/map/receipt/Batch-plan rebuild, new scope,
  or additional platform write is permitted. Additional platform reads are allowed only to repair
  the proof input.
- Cleanup may be deferred only while this bounded correction is eligible or active. Success or any
  terminal condition resumes the existing deletion, credential destruction, and evidence handoff
  without a new lifecycle.

#### Safe evidence contract

Raw native-verifier arguments, results, errors, MCP metadata, conversation text, thread IDs, secrets,
and continuation text MUST NOT be persisted. The raw tool error is visible only in the transient
Runtime conversation that the Protocol Agent already owns. Existing safe native-failure fields remain
unchanged:

```text
error_code
failure_layer
error_message_sha256
top_level_exact
types_valid
mode_create
```

The driver may additionally persist only these exact safe stage payloads:

- `native_verifier_attempt_observed`:
  `native_call_count`, `continuation_count`, `outcome` (`failure` or `success`), and nullable
  `failure_layer`;
- `protocol_continuation_started`:
  `agent_id="protocol"`, `continuation_count=1`, `native_call_count_before`, `failure_layer`,
  `same_agent=true`, `same_thread=true`, `same_run=true`, and `continuation_text_sha256`;
- `protocol_correction_terminal`:
  `native_call_count`, `continuation_count`, and `terminal_reason` from exactly
  `native_call_budget_exhausted`, `continuation_idle`, `non_correctable_failure`, or
  `continuation_delivery_failed`.

Counters are derived from deduplicated verifier call completions/failures. No event may include the
raw error, raw arguments/result, proof body, delivery text, Agent transcript, or an error-hash lookup
dictionary. Existing receipt/map/Batch-plan, verifier-success, Broker, cleanup, and gate evidence
remain authoritative and are not replaced by these observer stages.

#### Implementation impact candidates and test candidates only

No GitNexus impact analysis or implementation is authorized by this documentation round. A later
implementation round must inspect impact before editing these candidate symbols/files:

- `p2a_protocol_driver.run_driver`, `_idle_stage_error`, `_task_text`, and
  `_read_native_verifier_events` for counting, eligibility, fixed continuation, and terminal state;
- a new small pure eligibility/counter helper, if justified (**UNKNOWN** until indexed);
- the P2a driver contract and focused driver tests for the safe events and no-repeat invariants.

`CodexRuntimeAdapter.send_message` and `RuntimeDelivery` are read-only reused interfaces, not edit
candidates. `P2ACodexRuntimeAdapter`, `build_p2a_batch_plan`, both existing overlay tools, normal
Codex lifecycle semantics, `proof_v2.py`, platform routes, backend, and frontend are not expected to
change. The deferred builder symbols and both builder-schema review Highs are outside current impact
scope.

Future implementation tests must cover, but this documentation round MUST NOT run or add tests for:

- multiple same-turn verifier attempts consuming one shared counter without Host intervention;
- the exact eligible natural-idle state sending one `RuntimeDelivery` through `send_message`, starting
  a new turn on the same thread/Agent/run, and every missing predicate preventing continuation;
- exact existing Project/Ontology/Build Session/Lease and credential identities with unchanged
  original expiries passing the pre-delivery gate;
- any missing/invalid identity, identity or expiry drift, expiration, replacement, restore/recreate,
  or attempted Lease/Session/credential acquire/renew/extend being rejected without `send_message`
  and entering existing cleanup;
- correctable versus non-correctable failure layers and fail-closed ambiguous classification;
- three-call exhaustion across both turns, third failure in the original turn, continuation idle with
  unused call budget, continuation delivery failure, and prohibition of a second continuation;
- exact fixed continuation text/digest and absence of raw error, proof, transcript, thread ID, or
  secrets from persisted evidence;
- no repeated dry-run/apply/write, semantic change, candidate/map/receipt/Batch-plan rebuild, new
  scope, or premature Broker report across both turns;
- native `complete=true` followed by the Protocol Agent's own Broker report, with the Host remaining
  an observer/cleanup owner;
- unchanged exact-two overlay tools, retained receipt/map/Batch-plan mechanics, normal Adapter
  behavior, and frozen global asset/tool hashes.

These are planning candidates only. This amendment performs no code/test change, impact run, runtime
attempt, or acceptance claim.

### Round 76 current-minimal amendment: Coordinator-led independent semantic acceptance

This append-only amendment supersedes every conflicting Round 59–75 design statement that makes the
P2a driver, native verifier, native-proof builder, Round75 continuation, official P2a gate, or fresh
`t` the current semantic completion path. Those sections remain historical diagnosis and mechanical
design evidence only. The current path is one simple business slice produced by the existing team and
accepted by a fresh, independent, read-only Acceptance Agent. Round75 real execution and `t` are paused.

#### Responsibility boundary

- **Coordinator:** selects the next simple slice, freezes its immutable acceptance ticket, waits for
  Producer `ready_for_acceptance`, requests a fresh Acceptance Agent, validates only result binding and
  routes failures. It does not decide or rewrite semantic PASS.
- **Producer Agents:** Modeling owns ontology semantics and explicit unknowns; Protocol owns formal
  delivery through dry-run/apply and platform receipts. They may repair a routed failure, but their
  terminal report is only `ready_for_acceptance`, never PASS.
- **Acceptance Agent:** starts with a new Agent/session/thread/work directory and no Producer transcript.
  It directly reads the approved source bundle and the ticket-bound retained live state using only the
  frozen read allowlist, then returns `PASS|FAIL|BLOCKED`. It never repairs, writes, continues the
  Producer run, or mutates retained evidence.
- **Delivery/runtime mechanics:** may launch the requested runtime, bind identities and read-only
  credentials/tools, transport canonical envelopes, enforce timeouts, preserve evidence, and clean up.
  They cannot interpret business meaning or promote a mechanical success to semantic PASS.

During an acceptance round, the ticket-bound Project/Ontology/workspace version and source signature
are immutable. Producer writes are paused. Any state drift or write invalidates the round and requires a
new ticket and fresh Acceptance Agent. Acceptance resources—runtime directory, credential, process and
result evidence—have unique round ownership and are cleaned independently; the retained Producer model
and evidence are read-only and are not cleaned or rewritten by the Acceptance Agent.

#### Ticket and result envelopes

The canonical ticket schema is `r2-3-002-slice-acceptance-ticket/v1` with exactly the fields defined by
the Round76 requirement: `schema_version,ticket_id,slice_id,slice_revision,producer_run_id,model_state,
model_state_digest,source_bundle_digest,competency_questions,allowed_read_tools,timeout_seconds`.
`model_state` has exactly `project_id,ontology_id,workspace_version,source_signature,build_session_id`.
The Coordinator computes `ticket_digest` from canonical compact JSON and publishes the complete ticket
once. The current simple-slice default timeout is 600 seconds and the unapproved maximum is 1200.

The canonical result schema is `r2-3-002-slice-acceptance-result/v1`. It repeats the ticket identity,
slice/revision, full model state and digest, and source digest; adds `acceptance_round_id,ticket_digest,
verdict,failure_layer,checks,competency_question_results,evidence_refs,summary`; and permits verdicts only
from `PASS|FAIL|BLOCKED`. All eight checks—source fidelity, scope, ontology structure, explicit unknowns,
validation/reasoning, governed retrieval, Evidence/lineage and competency questions—must be explicit.

The Acceptance Agent receives no expected answers or PASS-shaped fixture. Each evidence reference must
resolve either to an approved source location/digest or a formal read from the frozen live state. It must
consume all required retrieval pages and distinguish modeled unknowns from missing evidence. Validation
and reasoning are allowed only through existing non-mutating compute/read operations. No submit/apply,
Build Session/Lease mutation, credential mutation, delete, repair or evidence write tool is allowed.

#### Verdict and repair state machine

```text
Producer revision ready_for_acceptance
  -> Coordinator freezes ticket
  -> fresh read-only Acceptance Agent reads approved sources + retained live state
  -> PASS: accept only ticket-bound revision/state
  -> FAIL: route one failure layer to its owner, repair as a new revision, issue a new ticket/round
  -> BLOCKED: preserve the missing condition, unblock without inventing evidence, issue a new round
```

Failure routing is fixed: `modeling-quality` to Modeling; `interview` to Coordinator for one bounded user
question and then Modeling; `protocol-delivery` to Protocol; `platform` to the platform implementation
owner; `runtime` to the Delivery/runtime owner. The Acceptance Agent reports evidence and the layer but
does not perform the repair. A repaired model must never reuse the prior verdict or Acceptance Agent
context. Slices may be accepted one by one; a fresh integration ticket/Agent evaluates the frozen union
after every included slice revision has PASS.

#### Reused mechanics and explicit non-authorities

Candidate receipt, candidate/map binding, exact Batch planning, dry-run/application identity, pagination
and cleanup helpers may remain because they protect deterministic delivery. Their unit or live success
is input evidence, not an acceptance verdict. P2a driver/native verifier/native-proof builder/Round75
continuation are diagnostic or future/contingent only and are removed from the current completion gate.
No official P2a gate is required or written, and no Round75 real run or fresh `t` may start under this
amendment.

The literal decision remains unchanged: current acceptance does not require real explicitly typed or
language-tagged literal writes. The slice should be deliberately small enough that modeling and each
acceptance round complete quickly; this amendment adds no general orchestrator, acceptance database,
background scheduler, auto-repair loop, management UI or productized policy framework.

#### Development and review consequence

Current code and contracts that require a P2a pass before `t` are implementation evidence, not the new
target. A later reviewed implementation handoff must make the smallest change needed to launch the fresh
read-only Acceptance Agent and carry these two envelopes while preserving existing Producer and platform
write correctness. This documentation amendment itself authorizes no code edit, test execution, P2a run,
semantic modeling start, platform write, gate creation or commit. Mandatory plan review and independent
Agent-led real acceptance remain pending.

### Round 76 plan-review High closure

This append-only closure accepts H1–H4 and supersedes conflicting Round76 implementation detail. It
does not create the planned assets or authorize code, configuration, tests, runtime, platform writes,
semantic starts, gates, or commits.

#### H1 — bounded producer-to-acceptance lifecycle

The implementation anchor remains `TeamTransportBroker.report`: Producer Agents still publish only the
existing terminal `TaskResult(status=completed|blocked)`. `ready_for_acceptance` is not a fourth Broker
status and does not alter terminal records. The bounded production sequence is:

```text
Producer revision frozen
  -> Coordinator publish_acceptance_handoff(ticket) once, before Coordinator completed
  -> Coordinator + Modeling + Protocol report existing completed terminals
  -> TeamRunner emits settled only after all terminal results and Runtime wait_settled
  -> Delivery retains non-empty Project/Ontology/model evidence
  -> Delivery stops every Producer Runtime and destroys/revokes every Producer write credential
  -> Delivery starts one Acceptance sidecar in a new root/session/thread/read credential
  -> Acceptance submit_acceptance_result(result) once through a separate carrier
  -> Coordinator/project-management layer routes the unchanged verdict
```

The handoff and result tools are task-scoped local Unix/file capabilities, not a scheduler or general
orchestrator. The sidecar cannot start while a Producer runtime/write key is active or before the three
completed terminals, settlement, retained handoff, and cleanup receipt exist. An optional summary may
later be sent to the old Coordinator thread, but it is non-authoritative and never a completion
dependency. Acceptance never rewrites Producer terminal evidence.

For retained run `r23002-real-20260801s` only, a new coordinating Agent may bootstrap the ticket from
the retained rev7 handoff plus settled/cleanup evidence even though the historical terminals are
blocked. This does not resume an old Agent session, create a Producer run, or mark a semantic start and
does not weaken the completed-terminal rule for future Producer runs.

#### H2 — credential and exact read surface

Static repository inspection confirms that API keys currently store only `project_id` and scopes from
`read|model|admin`; they have no Ontology/ticket/round/tool-list columns. Existing HTTP key creation and
revoke plus MCP per-call revocation and Project ownership checks are reusable. The narrow design layers:

1. a server-recognized, Project-scoped key with only `read`;
2. an immutable local credential manifest binding key ID to Project, Ontology, ticket digest, round and
   sidecar-config digest; and
3. an isolated MCP server config registering only the ticket allowlist.

Delivery owns creation/revoke and keeps all admin/model/Producer credentials outside the sidecar. It
revokes the read key and destroys plaintext/runtime secrets on every terminal path, retaining receipts.
This supplies the missing ticket/round/tool lifecycle binding without a database or security-model
extension.

Existing read tools, selected down to the ticket minimum, are:

| Category | Existing MCP tools |
| --- | --- |
| State | `check_platform_health`, `get_project_build_context`, `get_build_session`, `get_modeling_context`, `get_build_context`, `get_ontology_workspace_context` |
| Model/retrieval | `get_ontology_read_model`, `get_semantic_read_model`, `query_semantic_context`, `semantic_sparql_query`, `describe_semantic_graph_set`, `list_semantic_derived_pointers`, `inspect_semantic_projection_status` |
| Evidence/lineage | `list_evidence_references`, `get_evidence_reference`, `get_ontology_lineage`, `inspect_semantic_statement_provenance` |

`run_semantic_validation` and `run_semantic_reasoning` are existing `model`/mutating tools and are
forbidden. HTTP already exposes read-only list/get routes for validation and reasoning runs, but MCP
does not. The only platform implementation delta is four generic Project-owned read wrappers:
`list_semantic_validation_runs`, `get_semantic_validation_run`,
`list_semantic_reasoning_runs`, and `get_semantic_reasoning_run`. Lists require a ticket-bound
graph-set/Ontology scope; gets resolve run ownership. They delegate to current read services and make no
semantic-service or data-model change.

#### H3 — carriers, typed evidence and routing

The local acceptance root is separate from the Producer runtime root. `publish_acceptance_handoff`
exclusive-creates canonical `acceptance-ticket.json`; `submit_acceptance_result` exclusive-creates
canonical `acceptance-result.json`. Each carrier records its SHA-256 and refuses duplicate, overwrite,
symlink, escape or binding drift. Neither uses TeamTransport `TaskResult`.

`evidence_refs` is the exact union frozen in the Round76 requirement:

- `approved_source(type,ref_id,ticket_digest,source_bundle_digest,location,artifact_path,
  artifact_digest)`;
- `platform_read(type,ref_id,ticket_digest,model_state_digest,tool,request_digest,response_digest,
  artifact_path,page)`, where page contains
  `ordinal,input_cursor,output_cursor,has_more,sequence_complete` and forms a complete cursor chain.

The resolver validates only path/allowlist, existence, digest, ticket/model binding and cursor
completeness. It does not compare answers or infer verdicts. Result submission accepts `failure_layer`
as null only for PASS and requires one of the five layers for either FAIL or BLOCKED; a mechanical or
evidence gap stays BLOCKED rather than becoming semantic FAIL. It persists the Agent's verdict byte for
byte after canonical parsing.

Routing is fixed: modeling-quality→Modeling, interview→Coordinator/user,
protocol-delivery→Protocol, platform→repository developer, runtime→Delivery/runtime. If the owner is
outside the active roster, the coordinating layer retains BLOCKED and requests external delegation. It
does not rewrite the verdict, ask Acceptance to repair, or create an auto-repair engine.

#### H4 — acceptance-only, gate-free assets and retained-s bootstrap

Implementation must leave `modeling_team/tasks/r2-3-002-t.yaml` and its profile unchanged. It adds only:

- `modeling_team/tasks/r2-3-002-acceptance-s.yaml`;
- `modeling_team/profiles/r2-3-002-acceptance-sidecar.yaml`, with one Acceptance Agent; and
- `modeling_team/references/r2-3-002-acceptance-sidecar-config.json`.

Their schemas reject and their runtime surface cannot access `expected_matrix_binding`,
`semantic_start`, StartLedger mutation, P2a, native verifier/proof or official gate paths/tools. They
carry only the ticket/result paths, independent runtime identity, timeout, credential-manifest digest,
approved source mounts and exact read allowlist.

The first planned real ticket is the small `retained-s-c-published-output` slice: determine from approved
sources and live reads which published C version B binds and which output it consumes. Preflight must
re-read and bind Project `436040de-fbd4-47b5-8711-a95416379ea0`, Ontology
`e48272ff-bb82-4784-93e4-ccb39144e78d`, workspace
`7243849bf3c1d821bcb4852715f84e1dfa94f85a6097cdb5183adfe16976002a`, source signature
`b4b185ff1900edba0e46f72db4b6c633`, approved source-manifest digest
`20edb54595b8b4e3214b03b67fe5b357962f0d11ce5e928345126f4ce17d0b5c`, and retained-handoff
digest `98b2968fd04313bd8bc74efbbfe89a8f3f4ec42dce4d7c7abcfb2e9a49a3eafb`. Handoff is candidate
provenance, not an expected answer. Any drift or missing read capability yields BLOCKED with no P2a
fallback, official gate, fresh `t`, or semantic-start consumption. Typed/language literal validation
remains out of scope.

### Round 77 Agent-first operational acceptance reduction

Round77 supersedes the Round76 implementation-first sidecar/carrier plan. The current design is one
manual, bounded operational run using the existing collaboration/team Agent mechanism and existing
HTTP API. Acceptance package/profile loaders, integrated sidecars, carrier MCP, immutable response
proxies, per-Ontology enforcement and four validation/reasoning MCP wrappers are future productization
to reconsider only after real evidence exists.

The main coordinating Agent freezes one ticket under the gitignored
`workspaces/modeling-acceptance/<round>/`; Delivery performs owner/state preflight, creates a temporary
Project `read` key, records before inventory, and hands a fresh independent Acceptance Agent only the
key, base URL, ticket, approved sources and exact request allowlist. The Agent is not added to the
Producer roster and never resumes `s`. It may write raw requests/responses, hashes, typed refs and its
result only inside its unique evidence directory. Delivery then records after inventory, revokes the
key, proves it no longer authenticates, and cleans the Agent process/secrets.

There is intentionally no local carrier, resolver or enforcement proxy. The Agent returns the Round76
result directly; the coordinating layer checks binding/readability and routes the unchanged verdict.
Request records plus before/after inventory are the operational audit. An out-of-list request, missing
audit, retained-file mutation or state drift invalidates the round as BLOCKED. This is a local single-
Ontology experiment, not a generalized security claim.

Preflight requires the Project ontology list to contain only the target Ontology and confirms ownership
through actual response fields: Ontology `project_id`; workspace `ontology_id/default_graph_set_id/
source_signature`; modeling context `project.id/ontology.id/workspace_version`; graph set
`scope_type/scope_id/source_signature`; validation/reasoning item `graph_set_id/source_signature`;
semantic query scope P/O/workspace/source; read-model G/source; Evidence P/O/G; lineage O. Any ambiguity
blocks before Agent launch.

The exact Agent HTTP table, P/O/G/V/R values, pagination rules, CQ-bound context request, frozen SELECT,
Evidence IDs and lineage targets are authoritative in the Round77 requirement and are copied into the
ticket rather than reimplemented. Two non-mutating POST query routes are allowed; every other Agent
POST/PUT/PATCH/DELETE is forbidden. Validation/reasoning use only their `graph_set_id` list GETs because
the current run-ID ownership resolver does not cover those run types. No MCP wrapper is assumed.

The real object remains only `retained-s-c-published-output`; no Producer run, fresh `t`, semantic start,
P2a/gate or typed/language-literal claim is introduced.

### Round 78 fresh simple slice with inline Evidence

Round78 changes only Round77's target: retained s remains diagnostic/model evidence but cannot PASS
because its submitted platform Evidence was empty, and it is never patched post hoc. The one remaining
authorized semantic start creates exactly one fresh Project/Ontology and one <=12-item slice for the same
B-to-published-C-and-consumed-Output CQ. There is no fresh t, P2a, native verifier or official gate.

The current collaboration team runs four separated roles under the main Coordinator: fresh Delivery,
Modeling, Protocol and independent Acceptance. Modeling and Protocol use `terra-xhigh` where available.
Modeling sees sources plus CQ, never the expected answer, and gives every minimal item at least one inline
`evidence[{document_name,excerpt}]` plus explicit unknowns; cross-run `evidence_reference_ids` are forbidden.
Candidate operations are limited to fresh RDF creates for class/property/entity/relation/shape; delete and
rule-only operations are excluded because current modeling-item origin lineage is not guaranteed for them.

Delivery owns the sole ledger reserve/start and all resources, keys, directories, health checks and cleanup.
Protocol owns only formal transport: it may correct payload form from actionable API errors, with at most
three dry-run calls and one apply, but cannot alter semantics. Before apply, the actual candidate/batch and
successful dry-run operation plan must have matching item counts and non-empty, matching Evidence counts.
After apply, formal readback must resolve per-item EvidenceReference/Association IDs through Evidence
search/list and modeling-item origin lineage. Missing/mismatched Evidence blocks the write or acceptance;
P2a/other-run Evidence is never reused. Apply uncertainty or semantic correction need is BLOCKED without a
second semantic start. Producer-side validation/reasoning completes before all write keys are revoked.

Delivery then freezes a fresh-state ticket and a temporary Project `[read]` key. The fresh Acceptance Agent
uses the Round77 existing-HTTP read contract parameterized by the new P/O/G/run IDs, reads existing
validation/reasoning only, and independently judges source fidelity, scope, ontology structure, unknowns,
retrieval, Evidence/lineage and CQ. It cannot write or repair. PASS requires its semantic verdict, all keys
revoked, runtimes stopped, the non-empty model retained and ledger exactly +1. Empty failed scope may be
cleaned; applied non-empty failure is retained. Typed/language-tagged literal real-write validation remains
an explicit non-claim, and no product framework is added.

#### Round 78 High closure — active canonical writer before start

Delivery inserts one fail-closed gate before ledger reserve/start or any fresh resource/key creation. It
binds the active systemd unit, MainPID/start timestamp, 8001 listener/cgroup/cwd/command, backend `Settings()`
probe and authenticated `GET /api/semantic/canonical-mode` response into one preflight record. The HTTP
service must report `product_write_mode=rdf_primary` and agree with process/Settings evidence; the source
default or a static config value alone is never proof, and `legacy_only` is forbidden.

If wrong or missing while ledger/start remains unchanged, Delivery may change only the gitignored
`backend/.env` or authoritative unit environment key `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`, run the
Settings/config probe, restart `ontology-platform.service`, wait active, verify status plus backend 8001
health and frontend 5173, then repeat the active-mode binding against the new PID/start timestamp. Failure
is BLOCKED before semantic start. Configuration becomes immutable once ledger reserve/start occurs,
including cleanup. All candidate, inline Evidence, Protocol, independent Acceptance and retention gates
remain unchanged.

#### Round 78 acceptance Evidence-layer correction

The authoritative current chain is Modeling Batch inline EvidenceReference → current-run
`modeling_item` EvidenceAssociation → applied resource/statement origin lineage. Protocol retained
12/12 item readback, 15/15 associations, five references and resource lineage coverage; Acceptance must
independently resolve exact approved-source excerpts/digests and require supported, complete,
untruncated, warning-free lineage. These producer facts are not an Acceptance verdict.

`fact-audit-queue.evidence_bindings` is a separate FactEvidenceBinding surface and is not automatically
populated from Modeling Batch inline evidence. Its retained 7/7 `missing_evidence` result remains useful
diagnosis but is not a blocker when the modeling-item origin chain above is complete. The latest ticket
therefore adds exact-ID Evidence reference/association and resource/statement lineage GETs; fact-audit
may remain diagnostic only. A generic FactEvidenceBinding bridge/projection is future capability, not a
Round78 prerequisite. A fresh acceptance ticket/read key may re-evaluate the unchanged applied model
without a model write, ledger reservation or semantic start.
