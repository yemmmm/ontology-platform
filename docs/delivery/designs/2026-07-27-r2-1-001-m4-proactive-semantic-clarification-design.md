# R2.1-001 M4 建模 Agent 主动业务语义澄清执行设计

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M4
- Delivery record:
  `docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-27-r2-1-001-m4-proactive-semantic-clarification-test-plan.md`
- Status: accepted — implemented and independently verified through Round 30
- Scope version: M4 contract v1

## Goal

Prove, in a fresh isolated run of the accepted Dify `C -> B -> A` Workflow-as-Tool slice, that a
modeling Agent can distinguish documented facts from consequential missing business semantics, ask one
necessary question at a time, consume the answer safely, and make the resulting model behavior
observable through the normal governed semantic path.

The proof is behavioral. It does not require identical question wording, classes, IRIs, RDF text or
graph structure between runs.

## Current behavior and reused baseline

M3 already provides an isolated fresh-Agent launcher, immutable manifest staging, host-owned file-spool
API forwarding, response-consumption receipts, public Build Session completion, Modeling Batch dry-run
and `apply_atomic`, validation, reasoning, query, mutation acceptance and an isolated read-only consumer.
It only receives static inputs and therefore cannot prove whether a semantic decision came from source,
user clarification or an unsupported guess.

M4 reuses the M3 business boundary and formal platform path. It adds a new M4 scenario package rather
than changing M3's accepted launcher, tests or retained evidence. The M4 package may reuse M3 protocol
ideas and public contracts, but must be self-contained in its own input manifest, runner and tests.

## Functional contract

### Actors and boundaries

| Actor | Responsibility | Must not do |
| --- | --- | --- |
| Modeling Agent | Read only its sanitized input, identify material uncertainty, ask one question, choose and formally apply the model, and record its own chain of reasoning. | Read hidden answers or prior answer models; ask a user to choose RDF structure; use a bypass write path. |
| M4 host responder | Hold the hidden answer contract, validate and serially answer eligible requests, and retain a safe audit. | Choose ontology structure, emit Modeling Batch items, or write Agent artifacts. |
| Semantic Platform Core | Apply generic Modeling Batches and return deterministic validation, reasoning and query facts. | Interpret Dify-specific behavior or answer business questions. |
| Independent tester | Use withheld answer variants and queries to prove semantic differences, isolation and regressions. | Feed answer-model artifacts back to the Agent or relax behavior gates. |

The existing persistent interview and Modeling Workflow event APIs are intentionally not part of this
contract. They remain reusable platform capabilities, not M4 prerequisites.

### Fixed scenario and hidden decisions

The visible M4 brief keeps the accepted C scorer, B content generator and A publication chain, but states
three material facts incompletely. It must not identify which answer is correct.

| Decision area | Visible ambiguity the Agent must discover | Baseline hidden response | Withheld variant / expected semantic difference |
| --- | --- | --- | --- |
| Invocation lifecycle | Whether B's invocation of C follows C's Latest published Version or is pinned to a previous published Version. | B follows the Latest published Version. | A pinned-Version run must model and return the concrete older published C Version and its contract as B's current target. It must not rely on the absence of a Latest-target relation. |
| Output identity | Whether the new `quality_rating:number` contract is the documented successor of `quality_score:number`, rather than an unrelated addition. | It is a declared successor. | A non-successor run must explicitly model and return the distinct new-contract addition and old-contract removal/discontinuity as user-confirmed business facts. Missing a continuity edge alone is not evidence. |
| Missing-score handling | Whether B uses a confirmed fallback when scoring data is unavailable. | User cannot confirm it. The result is explicit unknown. | No run may turn this into a default, absence or confirmed business behavior without an answer. |

The first two baseline responses and their alternative contracts are only visible to the host responder
and independent tester. The third baseline response is deliberately `uncertain`. All three require an
Agent question because they change model boundary, current-target interpretation, relationship semantics
or consumer conclusions. Facts already stated in the brief, including the C/B/A identities and the
Current Draft versus Latest Version distinction, are not eligible user questions.

### Clarification transport

The new Agent prompt exposes a local, file-spool protocol separate from the existing platform API spool:

1. The Agent atomically writes one UTF-8 canonical request under
   `M4_CLARIFICATION_REQUEST_DIR` with `id`, `affected_terms`, `question` and `business_impact`.
   There is no Agent-visible enumeration of hidden decision areas or expected question count.
2. `affected_terms`, question and impact are all Agent-authored. The host responder uses its hidden
   contract to recognize whether their combined business meaning reaches an answerable ambiguity; it
   never requires an exact sentence or a prescribed ontology structure. A malformed or ineligible request
   receives `not_eligible`, not a semantic answer.
3. The responder accepts at most one unresolved eligible request. It maps a valid request to the hidden
   contract, writes a host-owned immutable response under
   `M4_CLARIFICATION_RESPONSE_DIR`, and appends a redacted audit entry. It rejects duplicate IDs,
   simultaneous open questions, malformed input, unsupported requests and response-path tampering.
4. A response has the same request ID and is either `answered` with one business answer, `uncertain`
   with a reason, or `not_eligible`. It never returns an ontology recipe, Batch payload, IRI, query,
   hidden-decision key or another answer.
5. The launcher mounts request files as Agent-writable and response files as host-owned read-only over
   the Agent workspace. It injects no answer data through the prompt, environment, API spool, command
   line or Agent-visible manifest.

The protocol does not disclose a hidden-decision checklist. Independent acceptance evaluates whether the
question's own terms and stated impact correspond to a material visible-input gap, while never comparing
wording. A question about a documented fact or an ineligible generic question cannot substitute for a
required clarification.

### Required answer-to-model chain

For every accepted response, the Agent's append-only decision log and runtime record must bind:

`request ID and question -> response bytes hash/status -> changed assumption -> changed immutable Batch
input or explicit-gap item -> dry-run/apply result -> validation/reasoning/query evidence`.

Answers are business decisions, not source Evidence. Official Dify excerpts and synthetic fixture text
remain direct Evidence; Agent decisions remain in modeling rationale, Checkpoints and the M4 decision
log. An uncertain response must produce a named explicit gap with its reason and must not cause a
confirmed fallback or absence assertion.

## Implementation shape

Add `docs/evaluation-scenarios/dify-workflow-impact-m4/` with:

- `business-brief.md`, a sanitized M4 contract, Agent prompt, generic Modeling Batch command contract and
  immutable input manifest;
- an M4-specific launcher, host clarification responder and API file-spool gateway integration that retain
  M3's fresh process, temporary Codex home, mount audit, response receipt, secret scan and Build Session
  completion properties;
- an M4-specific read-only consumer launcher/gateway or an explicitly audited reuse wrapper; and
- focused unit tests plus tester-owned acceptance specs and result summaries.

The M4 launcher starts the responder outside the namespace, layers the host response directory read-only
on the Agent workspace, retains request/response hashes and proves the complete hidden answer contract
is not mounted. The existing API spool remains the only path to the platform. Its normal receipt and
Build Session obligations are retained with M4-specific names and hashes.

No code under `backend/`, `frontend/`, `backend/migrations/` or the accepted M1–M3 scenario packages is
in scope. If the isolated experiment cannot express a safe pause/question/answer/continue loop, stop,
record a minimal proof, and refine a separate generic platform requirement before changing those layers.

## Round-12 runtime-discovered platform exception

Round 12 proved that the pause/question/answer/continue loop works, but the first principal
Shape-containing Modeling Batch returns HTTP 500 before the ABox stage. The reproduced failure is
generic and deterministic: `_compile_shape_node` derives a Turtle blank-node label directly from
Agent-supplied `shape_id` and `path_id`; valid public IDs such as `urn:m4:WorkflowShape` and
`urn:m4:workflowKey` therefore produce a blank-node token containing an illegal colon. The same payload
uses the public product datatype name `string`, while `_datatype_iri` currently treats it as a relative
IRI instead of `xsd:string`.

The current minimal exception to the original scenario-only boundary is limited to:

- make compiler-generated Shape property-node identities deterministic valid RDF blank-node labels for
  arbitrary accepted IDs, without changing the modeled Shape meaning or merging distinct
  Shape/constraint identities;
- normalize only a recognized bare XML Schema datatype local name such as `string` to its XSD IRI while
  preserving the already supported `xsd:*` and arbitrary absolute-IRI forms; and
- add a Modeling Batch regression using URN-shaped class/property/Shape IDs and bare `string` that proves
  the representative principal schema dry-run returns `mode=dry_run`, `attempt_status=validated` and no
  blocking finding rather than merely replacing the unhandled RDF parser exception with
  `validation_failed`.

This exception does not add a new API, storage model, retry, Shape relaxation, Dify-specific branch or
fixed answer payload. It exists only to let the already reviewed generic Modeling Batch path consume the
public command values generated by the autonomous Agent. The existing M4 correction and acceptance
contracts remain unchanged.

## Round-14 runtime-discovered `sh:in` compiler exception

Round 14 passed the repaired principal schema dry-run and apply, then correctly obtained a blocking
finding for the intentional invalid instance. The first autonomous candidate ABox dry-run nevertheless
returned HTTP 500. The backend traceback is deterministic:
`pyshacl.errors.ConstraintLoadError: InConstraintComponent must have at most one sh:in predicate`.
The compiler currently emits one direct `sh:in` predicate per `enum_values` member, but SHACL requires
one `sh:in` predicate whose object is an RDF list.

The current minimal exception is therefore limited to `_compile_shape_node`:

- compile each present `enum_values` collection as exactly one `sh:in` pointing to a well-formed RDF
  collection;
- derive every collection blank-node label deterministically from the owning Shape/constraint identity
  and list position, using Turtle-valid labels that cannot merge across constraints; and
- add an Agent-equivalent multi-Shape service regression that applies enum-bearing Shapes and then
  dry-runs both an allowed and a disallowed ABox value. Both calls must return governed Modeling Batch
  responses; the allowed value must validate and the disallowed value must return a structured SHACL
  finding, never an HTTP 500 or `ConstraintLoadError`.

This repair does not change the enum values, weaken a Shape, add retry behavior, inject a fixed M4 ABox,
or modify API/storage/canonical validation contracts. After independent offline PASS, acceptance may run
one new fresh autonomous baseline. Variant, consumer and mutation cases remain gated on that baseline
reaching authoritative `COMPLETED`.

Round 14 also exposed an independent clarification-path defect before the same schema request. The
Agent's output-continuity question was semantically equivalent to the ambiguity stated in the visible
brief, but `_decision_for` also matched its impact sentence to the lifecycle decision merely because it
mentioned B, C and a published contract. The responder therefore returned `not_eligible`; the Agent did
not revise that question or ask the remaining visible missing-score question before starting modeling.

The minimal clarification repair is:

- narrow lifecycle recognition to an actual invocation/current-target expression, so the exact
  Round-14 output-continuity request maps to only the output-identity decision; retain fail-closed
  rejection for a request that genuinely combines multiple decision questions;
- state in the Agent prompt that every consequential ambiguity explicitly listed in the visible brief
  must receive one eligible response before the principal schema Batch, and that `not_eligible` leaves
  that ambiguity unresolved and requires a revised question or `BLOCKED`; and
- make the host completion/timeline audit require one eligible, hash-bound response for each of the
  three visible brief ambiguities before the first principal schema request. This audit uses host-owned
  request/response evidence and does not disclose hidden answers, categories or an ontology recipe to
  the Agent.

This does not add a generalized dialogue engine or reveal a hidden checklist: the three uncertainties
are already literal input in `business-brief.md`. It only prevents a false-negative recognizer result
and prevents a run from claiming success after skipping a listed business decision.

## Round-16 runtime-discovered resource-ID integrity repair

Round 16 behaviorally passed all three required clarifications before any platform modeling call.
Project, Ontology and Build Session creation also succeeded. The lease request then used the prior
workspace-context response SHA-256 as `{session_id}` instead of the created Build Session ID and received
`build_session_not_found`. A host-side read of the actual created session returned HTTP 200. The exact
Agent helper declared `s` inside a Bash function without `local`, overwriting the outer `s` that held the
session ID; no Modeling Batch was submitted.

This is an Agent execution-integrity defect, not a platform persistence or lease defect. The minimal
repair is limited to the visible Agent prompt/command contract:

- persist each returned Project, Ontology and Build Session ID in `runtime-record.json` immediately;
- construct every resource-scoped request path from the corresponding runtime-record value just before
  atomically publishing the request, rather than from a mutable shell variable retained across helper
  calls;
- when Bash helpers are used, declare their scratch variables `local`; and
- before publishing a scoped request, assert that the path's resource ID equals the persisted runtime
  ID. A local mismatch is corrected before publication or makes the run `BLOCKED`; it is not sent as an
  API attempt.

Focused tests must freeze these instructions and the input-manifest hash. No platform API, database,
lease behavior, retry allowance, fixed ontology payload or generalized shell framework is added. After
independent offline PASS, one new fresh unsupplemented baseline may run; later acceptance stages remain
gated on `COMPLETED`.

## Round-18 Unicode canonicalization compatibility repair

Round 18 reached the first required clarification and correctly stayed before platform setup, but the
host rejected its request as non-canonical. The request was sorted, compact JSON with the allowed final
line ending. Its only byte-level difference was Python's default `ensure_ascii=True` representation of
the typographic apostrophe (`\u2019`) while the responder's canonical encoder writes the equivalent
UTF-8 character directly. The Agent locally revalidated the request using the same standard Python
encoding and waited for a response that the fail-closed responder never creates.

This byte-style distinction has no modeling or business meaning. The minimal repair is confined to
clarification request parsing:

- accept either sorted compact JSON Unicode rendering: direct UTF-8 (`ensure_ascii=False`) or standard
  JSON `\uXXXX` escaping (`ensure_ascii=True`), with the existing optional single final line ending;
- normalize both accepted forms to the existing direct-UTF-8 canonical bytes for semantic recognition,
  canonical request hashing and downstream evidence;
- retain rejection of unsorted keys, extra whitespace, duplicate keys, malformed Unicode/JSON, invalid
  envelopes and every other trailing/internal byte variation; and
- add paired direct/escaped Unicode tests proving identical parsed content and canonical hash, plus
  negative tests proving the existing strict boundary remains.

No business matcher, hidden answer, response format, API, retry, credential or ontology payload changes.
After independent offline PASS, one fresh baseline may run under the existing stage gates.

## Round-21 final-audit evidence-continuity repair

Round 21 completed the real modeling workflow: all three material clarifications were consumed before
modeling, the principal schema and Shape were validated and applied, the instance data was validated and
applied, semantic validation/reasoning/query succeeded, and the Build Session reached `completed`.
The host final audit nevertheless returned four errors caused by incompatible audit assumptions.

The repair is limited to the M4 audit contract:

- require one graph-set ID across the schema, intentional invalid-instance, candidate-instance and any
  correction evidence;
- require schema dry-run and schema apply to share `source_signature_before`, then require the schema
  apply's non-empty `source_signature_after` to equal the intentional invalid-instance and first candidate
  `source_signature_before`;
- within the direct-success branch, require candidate dry-run and apply to share
  `source_signature_before`; within the correction branch, require the failed candidate, correction
  dry-run and correction apply to share it. This proves state continuity without incorrectly requiring
  the pre-schema and post-schema signatures to be equal;
- validate the existing `optional_rule_absent` evidence using the prompt's `code`, `message`,
  `request_id` and `response_sha256` fields; and
- validate checkpoint and complete revision continuity using the recorded `checkpoint.session_revision`,
  which is the revision returned in the checkpoint response's Build Session.

The prompt and frozen input manifest do not change. Regression tests must reject a cross-phase signature
splice, wrong optional-warning evidence, and checkpoint/complete revision mismatches. The preserved
Round-21 evidence is re-audited from a copy; the original evidence remains unchanged. This repair does
not rerun the live Agent, weaken SHACL gates, alter a model payload, or substitute for later variant,
consumer and mutation acceptance.

## Round-22 fresh-workspace role interpretation repair

The first withheld variant completed all three clarifications and created fresh platform resources, then
stopped before lease acquisition because its local helper looked for a shortened `data` graph role. The
authoritative workspace response correctly returned `asserted_ontology`, `asserted_data`, `shapes` and
`policy`; zero resource counts and empty initial content hashes were also correct for a new Ontology.

The generic modeling command contract must therefore state that:

- workspace member `role` values are authoritative and must be used exactly as returned;
- the current platform roles are `asserted_ontology`, `asserted_data`, `shapes` and `policy`;
- a fresh workspace with those required members, empty content hashes and zero resource counts is ready
  for the first Modeling Batch, not missing schema/data; and
- an Agent may block only when required members are actually absent or the workspace reports a non-ready
  state, not because an authoritative role was locally abbreviated.

This is generic platform vocabulary, not a Dify ontology recipe. The protected command-contract hash,
input manifest and frozen manifest hash change together, with focused manifest/staging regressions. After
independent offline PASS, exactly one new fresh withheld variant may run; no fixed schema/ABox, retry of
the failed run, or platform behavior change is introduced.

## Round-24 entity-property IRI consistency repair

The next withheld variant exercised the live correction branch: the first candidate ABox failed SHACL,
the Agent produced one corrected ABox, and that correction passed dry-run. Applying the unchanged
validated correction then entered recovery because Oxigraph rejected bare entity-property predicates
such as `is_latest` and `version_number` with `Expected RDF IRI`.

The compiler already expands a bare entity class ID through the platform namespace, and schema properties
created from bare `property_id` values use the same namespace. Entity `properties` keys must follow the
same contract:

- in `create_entity` and `update_entity`, a non-empty property key containing `:` remains an explicit IRI;
- a non-empty bare property key is expanded with `ns.resource("property", key)`;
- invalid empty/non-string keys fail compilation before dry-run; and
- dry-run and apply continue to use the exact same compiled delta.

Focused compiler tests cover create/update expansion and explicit-IRI preservation. A Modeling Batch
service regression must dry-run and apply an entity containing bare property IDs against matching schema
properties, proving the RDF store receives only absolute predicate IRIs. This does not change Shape
semantics, correction limits, domain modeling, or persistence architecture.

## Round-26 blind-consumer transport and scope repair

The completed variant model passed independent read-only semantic queries, but the first blind consumer
could not reach the platform. Its prompt named an API spool without defining the canonical request
envelope or strict `<id>.json` filename, and the runner did not stage the promised Project/Ontology scope.
The consumer created five invalid filenames, received no response, correctly stayed `BLOCKED`, while the
wrapper incorrectly reported `COMPLETED` merely because the process exited zero and a record existed.

The minimal consumer repair is:

- require the runner to receive the accepted Project, Ontology and graph-set IDs and stage only those IDs
  in a read-only `consumer-scope.json`; before launch, the host verifies that the Ontology belongs to the
  Project and that its default graph set matches the supplied graph-set ID;
- give the consumer the exact bodyless-GET spool envelope, canonical JSON rule, request-ID/filename rule,
  response location and receipt hashing rule;
- run the read-only gateway with that verified scope and allow only necessary exact Project/Ontology GETs
  plus scoped Ontology/graph-set read-model GET prefixes. Global lists, foreign IDs and every write remain
  rejected before forwarding;
- define an answer-neutral task with three required observation slots: current C target/version and B
  contract, output continuity/discontinuity, and missing-score state. Each slot must cite successful
  in-scope receipt IDs/hashes; `unknown` is valid only when a positive explicit-gap fact is observed, not
  when data is absent; and
- define a small `consumer-record.json` terminal contract containing the verified scope, successful read
  receipts, the three observations/claim classifications, and `terminal_status: CONSUMER_READY`; and
- let the wrapper report `COMPLETED` only when that record is structurally valid, matches the supplied
  scope, all observation evidence binds to corresponding successful host gateway entries, the explicit
  gap backs `unknown`, and the process exits zero. A `BLOCKED` record, irrelevant single receipt, missing
  observation or zero forwarded requests cannot be completed.

The supplied scope contains no hidden decision, expected answer, ontology recipe or modeling log. The
consumer remains read-only. Focused tests cover staging, canonical transport, no-response/blocked
false-positive prevention, foreign/unscoped request rejection, missing/unbound observation rejection and
valid completion. The preserved Round-26 model may then be read again by a new consumer; the modeling
Agent is not rerun.

## Round-28 blind-consumer read-model discovery repair

The repaired consumer transport and scope gates worked: invalid/global requests were not forwarded and
the wrapper preserved the Agent's `INCONCLUSIVE` result. The consumer nevertheless saw only Project and
Ontology metadata because the answer-neutral prompt did not explain how to discover the platform's scoped
semantic read-model URLs.

The prompt must direct a consumer to first GET the supplied Ontology's `modeling-context`, then use only
the returned `query_entries` REST URLs needed for entities and facts. It must not invent shorter paths.
The platform `facts` entry already executes `statement-list`, whose SPARQL selects subject, predicate and
object, but the common row decorator currently discards those bindings. The generic facts projection must
therefore return:

- `subject`, `predicate` and `object`;
- whether the object is an IRI or literal; and
- literal datatype/language when present.

Existing envelope, provenance, assertion, staleness and display fields remain unchanged. Backend tests
must exercise both the graph-set `statement-list` service and public Ontology `facts` route with real
predicate/object bindings. The consumer wrapper's three semantic observation receipts must correspond to
successful scoped `semantic-read-models` requests; Project/Ontology metadata or modeling-context alone
cannot satisfy an observation slot.

The answer-neutral terminal record has one exact shape. `observations` contains the Agent's actual
non-empty conclusions, while the same-named `receipts` and `claim_classifications` bind and classify
those conclusions:

```json
{
  "terminal_status": "CONSUMER_READY",
  "scope": {
    "project_id": "<supplied-project-id>",
    "ontology_id": "<supplied-ontology-id>",
    "graph_set_id": "<supplied-graph-set-id>"
  },
  "receipts": {
    "current_target_contract": {
      "request_id": "<semantic-read-model-request-id>",
      "canonical_request_sha256": "<sha256>",
      "response_sha256": "<sha256>"
    },
    "output_continuity": {
      "request_id": "<semantic-read-model-request-id>",
      "canonical_request_sha256": "<sha256>",
      "response_sha256": "<sha256>"
    },
    "missing_score": {
      "request_id": "<semantic-read-model-request-id>",
      "canonical_request_sha256": "<sha256>",
      "response_sha256": "<sha256>"
    }
  },
  "observations": {
    "current_target_contract": {
      "current_target": "<non-empty observed target>",
      "target_version": "<non-empty observed version>",
      "b_contract": "<non-empty observed contract>"
    },
    "output_continuity": {
      "old_contract_change": "<non-empty observed change>",
      "new_contract_change": "<non-empty observed change>",
      "continuity": "<non-empty observed continuity conclusion>"
    },
    "missing_score": {
      "state": "unknown",
      "explicit_gap_observed": true,
      "gap": "<non-empty explicit modeled gap>"
    }
  },
  "claim_classifications": {
    "current_target_contract": "source",
    "output_continuity": "source",
    "missing_score": "source"
  }
}
```

Each classification value may independently be `source`, `synthetic`, `inference` or `judgment`; the
example values do not prescribe the answer. The wrapper validates the exact slot/key structure,
non-empty conclusion strings, explicit positive gap, classification enum and semantic receipt binding.
It does not compare conclusions to hidden expected values; independent acceptance checks their meaning.
Focused tests freeze this discovery sequence and reject missing/empty observations, malformed
classification shapes, metadata-bound slots and a receipts-only record. After the full backend suite,
normal service restart/health checks, isolated-backend restart and a live facts-content check on the
preserved variant model, one new consumer may run without rerunning modeling.

## Failure behavior and operational constraints

- A malformed, duplicate, unrecognized or concurrent clarification request is fail-closed and the run
  cannot claim `DEVELOPMENT_READY`.
- A responder timeout, missing response, missing response receipt, hidden-contract mount leak, or host
  answer in an Agent-visible artifact makes the run `BLOCKED` or `INCONCLUSIVE`.
- A question about a fact explicit in the visible brief is retained as evidence of an unnecessary question
  and fails the relevant M4 acceptance case.
- A platform validation failure can lead to an Agent correction, but cannot erase the question/answer
  history or be bypassed through direct RDF, semantic edit, dataset load or `validate=false`.
- A pure scenario-only change does not restart the normal service. Round-28 changes the shared backend
  facts projection and is therefore an explicit exception: after the full backend suite it must restart
  and health-check `ontology-platform.service`. A temporary isolated `rdf_primary` backend is allowed
  only for the formal acceptance run and must be stopped before closure.

## Acceptance summary

M4 is accepted only when fresh baseline and withheld-variant runs demonstrate that the Agent independently
finds all necessary decision gaps, asks them serially, applies answers through formal Modeling Batches,
and produces observable current-target/continuity behavior changes. Variant behavior must return the
positive user-confirmed alternative facts, not merely omit baseline facts. The unknown branch must remain
explicit through the read-only consumer. Input isolation, source fidelity, invalid-shape rejection,
inference, query, receipt/audit integrity, M1–M3 regressions, runtime cleanup and an independent PASS
remain mandatory.
