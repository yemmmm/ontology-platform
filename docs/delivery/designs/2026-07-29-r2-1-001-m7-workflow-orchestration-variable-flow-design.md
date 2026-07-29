# R2.1-001 M7 Workflow 编排与类型化变量流转设计

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M7
- Delivery record:
  `docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`
- Pause closeout:
  `docs/delivery/records/2026-07-29-r2-1-001-m7-paused-closeout.md`
- Status: reviewed — mandatory plan review Round 2 PASS
- Contract version: `m7-contract-v1`

## Goal

Extend the accepted Workflow-as-Tool slice into one bounded Workflow orchestration module and prove
that a fresh modeling Agent can reuse or explicitly evolve existing identities, model internal typed
variable flow and branches, preserve explicit unknowns, and support complete governed consumption.

The first module is B, `Content Generation Workflow`:

```text
Start(topic:string, channel:string)
  -> LLM(draft_content:string)
  -> Tool Invocation(C Version 2, quality_rating:number)
  -> IF/ELSE
      -> passing -> Template(publishable_content:string)
      -> failing -> manual review
  -> Output(approved_content:string)
  -> A.publish_content
```

M7 is an ontology-data experiment. Workflow, Node, Variable and business branch semantics do not
become platform product concepts.

## Current minimal scope

- One frozen accepted base slice, one B Workflow Version, no A/C internal graphs.
- Selected immutable English official sources plus one clearly synthetic business Fixture.
- At most six core Nodes, two branches, one external Workflow call and about ten
  variable/binding/use relationships.
- One fresh Codex modeling subagent for L1 and one independent fresh run for L2. The initial ceiling
  was three modeling attempts; after all three failed before principal apply on reproduced
  Runtime/scenario-contract defects, the evidence-based one-time recovery ceiling is five.
- One Runtime-neutral semantic package, one invalid candidate, validation, reasoning and governed
  queries.
- One blind read-only Consumer and four deterministic mutations after L1.
- Scenario-local files and deterministic scripts only. Backend code changes are not planned.

## Future productization

The following are not M7 completion requirements:

- a generalized Agent Runtime or adapter plugin framework;
- cross-Ontology import, IRI mapping or distributed composition;
- OS/network sandboxing, Provider proxy, permanent credential broker or cross-machine coordination;
- a complete Dify ontology, additional Node families or bulk real business data;
- M3's twenty-environment mutation matrix;
- polished management UI, immutable platform audit expansion or automatic crash recovery.

## Frozen functional contract

### Sources and truth boundary

Agent-visible official sources are:

- M1 Workflow-as-Tool `tools.mdx`;
- the frozen Dify foundations English pages for Orchestration Logic, Start Node, LLM, IF/ELSE,
  Template, Output and Version Control.

The synthetic business brief defines the C/B/A Fixture. Official product statements, synthetic
business facts, clarification answers and Agent inference remain separately attributable. Chinese
counterparts, the full corpus, hidden acceptance files, prior answer models, Batch payloads and
historical run evidence are not Agent-visible.

### Same-Ontology extension

Every attempt creates a new Project, Ontology, Build Session, Agent state and run root. The Host first
applies the hashed base semantic package into the fresh Ontology. The Agent then extends that same
Ontology. Historical platform IDs or prior run state are never reused.

The public base snapshot contains the accepted Workflow/Workflow Version/Tool Invocation/Variable/
Variable Binding/Variable Use facts, C score-contract continuity, missing-score explicit unknown and
B-to-C/A-to-B topology. The Agent must reuse its public semantic identities or record an evidence-based
evolution; an unrelated duplicate model fails.

### Provisional business-answer contract

The user delegated these answers to the main Agent. Contract `m7-contract-v1` freezes:

- a failing score produces no `approved_content` and routes to manual review;
- Template `publishable_content` and Workflow Output `approved_content` are distinct variable
  identities connected by an explicit binding;
- a missing score routes to manual review, retains `explicit_unknown` as the decision basis and
  produces no `approved_content`.

These are versioned modeling hypotheses. Evidence may justify a later contract version, but never a
mid-run change or retroactive rewrite.

### Capability questions

1. Starting from A's `publish_content`, return the complete typed production, binding and consumption
   path through B's internal Nodes and C invocation.
2. Distinguish passing, failing and missing-score behavior, branch-local variable availability, and
   certain-available/certain-unavailable/explicit-unknown results.
3. For C output name, type or availability changes, return only the B Nodes, branch condition,
   Template, B Output and A Binding connected by a real variable path.

M1 published/draft isolation, C-to-B-to-A reachability and invalid-structure rejection remain
regressions.

## Artifact layout

Implementation adds one scenario:

```text
docs/evaluation-scenarios/dify-workflow-impact-m7/
  README.md
  agent-input/
    task.md
    business-fixture.md
    official/...
    base-slice-public.json
    manifest.json
  base-slice/
    semantic-package.json
    manifest.json
  host-only/
    answer-contract-v1.json
    acceptance-contract.json
    mutation-contract.json
  attempts.jsonl
  runtime/
    .gitignore
  m7_contract.py
  m7_host.py
  tests/
    test_m7_contract.py
    test_m7_host.py
    test_m7_mutations.py
```

Runtime evidence is stored under a unique run directory. Stable compact acceptance evidence may be
committed; credentials, temporary Agent homes, provider transcripts with secrets and mutable platform
state are never committed.

`attempts.jsonl` is the scenario-global append-only modeling-attempt ledger. The Host validates and
appends `modeling_started` before launching a subagent. It is outside every per-run root, is never
removed by run cleanup and rejects a fourth start across all L1/L2 runs.

## Runtime-neutral Host spine

### 1. `prepare_scope`

1. Verify the frozen base package and source manifests.
2. Create a fresh Project and Ontology with a unique owned run tag.
3. Start a Build Session and read current context.
4. Dry-run the exact base package, then immediately before apply re-read session/context and acquire a
   fresh lease.
5. Atomically apply the exact dry-run items.
6. Record request/content hashes, resource outputs, workspace versions and base query proof.
7. Publish only the public resource map and base summary into the run-specific Agent input.

The base package is scenario-owned deterministic setup, not a hidden expected M7 answer. It contains
only accepted prior-slice facts and is applied before the Agent extension.

### 2. `stage_inputs`

The Host verifies exact file membership and SHA-256 values, then adds a run manifest containing only
the Project/Ontology IDs, public base-resource map, contract version and permitted clarification/package
locations. Hidden answer/acceptance/mutation files remain outside the Agent-visible root.

The modeling subagent starts with `fork_turns=none` and receives only the Agent-visible directory and
the allowed collaboration protocol. It must declare its input files and must not search the repository
or other run roots.

### 3. Agent clarification and semantic package

The Agent first records a source-completeness assessment. It asks at most five material business
questions, one at a time. A question must cite visible evidence and state the model or consumer result
that depends on the answer. Generic questionnaires, repeated explicit facts and requests for ontology
implementation decisions do not count.

The Agent produces one immutable `semantic-package.json` containing:

- `schema_version`, `contract_version`, base/source manifest hashes and Agent/run identity;
- a decision list binding each accepted clarification or explicit unknown to visible evidence;
- ordered Modeling Items using published `command_kind` values, stable `client_item_id`,
  same-Batch `item_ref`, dependencies, inline evidence/rationale and CQ bindings;
- a principal module candidate with schema, executable Shape, instances and relations;
- a separate invalid candidate designed to violate one Agent-authored module constraint;
- public role bindings identifying the resources required by CQ evaluation.

The package may use the platform's existing `item_ref` grammar inside a Batch. Across already applied
base resources it uses the exact public resource map supplied by the Host. Every role contains both
`resource_id` and `resource_iri`; the package schema fixes the allowed representation by command field:

- ID-only fields use `resource_id`, including `create_property.class_id/object_class_id`,
  `create_relation_type.source_class_id/target_class_id`, `create_shape.target_class_id` and Shape
  `constraints[].path_id`;
- IRI fields use `resource_iri`, including `create_relation.source_entity_iri/relation_type_iri/
  target_entity_iri` and direct RDF fact subject/predicate/object references;
- fields explicitly accepting a legacy ID or IRI follow their published compiler contract.

The Agent selects the correct published value; the Host validates the command/path type but performs no
ID/IRI conversion or semantic rewrite. Passing an IRI to an ID-only field, an ID to an IRI-only field,
or using an unknown placeholder fails before dry-run.

### 4. `apply_semantic_package`

The Host validates package schema, manifest binding, scope ceiling, allowed command kinds and immutable
candidate hashes before any write.

Execution order is:

1. principal extension dry-run;
2. principal extension `apply_atomic` using the exact same items;
3. invalid candidate dry-run, which must fail with a SHACL/semantic finding and must never apply;
4. optional ABox dry-run/apply only when the Agent package separates schema and instances.

Mechanical fields—Project/Ontology/Build Session IDs, expected workspace version, lease token,
idempotency key and canonical JSON envelope—are Host-owned.

No lease acquired before Agent reasoning is relied upon. Immediately before every `apply_atomic`, the
Host:

1. re-reads the Build Session and context;
2. verifies active session, exact Project/Ontology, unchanged expected workspace version and frozen
   candidate hash;
3. acquires/rotates a fresh lease; and
4. submits the same `client_batch_id`, canonical semantic items/content hash and apply idempotency key.

If the platform returns one precise `lease_expired` before an attempt is persisted, the Host may
re-acquire once, re-read the same context and resubmit the unchanged request except for the lease token.
It must not `renew` an expired lease. A second expiry, any other error, workspace/scope/items/hash drift,
an existing nonterminal attempt or uncertain commit fails closed. Audit evidence proves that at most
one apply committed and that no duplicate semantic submission occurred.

### 5. `validate_and_query`

The Host runs managed validation and configured reasoning, then:

- executes the Agent's own governed query checks if present;
- executes tester-owned read-only CQ assertions over public facts;
- uses bounded ontology-scoped SPARQL as the authoritative CQ proof when both primary matches and
  related context could paginate;
- permits Semantic Context Query for discovery or single-stream pagination only, never sends
  `match_cursor` and `context_cursor` together, and fails if a required stream remains truncated;
- fails on truncation, degraded completeness, stale scope or missing role-bound proof;
- checks all three M7 CQs and M1 regressions without assigning business severity.

The Host records result IDs, hashes, completeness metadata and exact public proof resources. It does
not generate an answer from expected constants.

### 6. `record_and_cleanup`

On success the Host checkpoints and completes the Build Session. On failure it preserves evidence and
marks the attempt terminal without continuing semantic writes. Unique resources are deleted only after
the independent tester has captured required evidence. Cleanup verifies resource absence and normal
service health.

## L1 and L2 acceptance

### L1

L1 requires base identity reuse/evolution, autonomous clarification, an immutable semantic package,
successful formal application, an executable constraint with a rejected invalid candidate, conforming
validation, consistent reasoning, complete new/old CQ results and clean isolation evidence.

### L2

After L1:

- a fresh blind Consumer answers all M7 CQs and M1 regressions through public reads;
- a second fresh modeling attempt produces semantically equivalent business conclusions, identity
  reuse and explicit-unknown behavior;
- deterministic isolated mutations remove the score binding, introduce a type mismatch, violate
  branch-local Output availability and add an unrelated same-name decoy.

The first three mutations must change validation/CQ results. The decoy must not create a false path.
Mutation execution does not invoke a modeling Agent.

## Failure classification and platform interruption

Every failure is classified as:

- `modeling-quality`: missed/redundant identity, invented default, incomplete package or wrong semantic
  conclusion;
- `platform-contract`: a generic accepted package cannot be faithfully applied, validated or queried;
- `runtime/infrastructure`: Agent/provider/process/transport/credential failure.

A platform interruption requires a minimal reproduction proving a generic platform gap that blocks or
materially harms modeling quality, semantic retrieval quality or applied-model integrity, with no
acceptance-preserving scenario-local path. It becomes a separate requirement and must independently
pass design review, implementation, testing, restart/health and commit before M7 resumes the same frozen
contract. Dify-specific or convenience changes are follow-ups only.

## Implementation and rollout

The initial implementation changes documentation and the M7 scenario only. If implementation later
needs to edit an existing backend symbol, GitNexus impact analysis and the platform-interruption gate
run before the edit. Backend changes require the full backend suite and service restart; scenario-only
changes require focused scenario/M1/M6 regressions, Ruff and normal runtime health checks.

M7 can be completed only after independently recorded PASS evidence covers L1, blind Consumer,
repeat, four mutations, M1 regressions, cleanup and runtime health. The experiment is currently
paused before L1; working test-plan results were consolidated into the pause closeout and delivery
record before that test document was removed.

## Attempt-3 v3 hardening after live evidence

Attempts 1 and 2 proved two scenario Host/Agent contract gaps before any principal dry-run:

- v1 did not expose the exact package and Modeling Item authoring protocol;
- v2 exposed that protocol, but its frozen `python ...` sealing command was not executable in the
  clean Agent shell, which provides `python3` but no `python`.

The final attempt uses `m7-contract-v3`. Historical attempts, packages, scopes and ledger events remain
immutable. v3 keeps the same business hypotheses and source corpus; it changes only the mechanical
runtime and CQ-proof contract.

### Executable sealing contract

- The staged helper is executable and uses a portable Python 3 shebang.
- The sole visible command is `./seal_semantic_package.py --agent-visible .`; no alternative command
  or hand-computed hash is permitted.
- Before `prepare` returns `PREPARED`, the Host runs the exact staged executable in a clean-shell
  runtime-check mode. It verifies interpreter availability, working-directory confinement, staged
  membership and zero semantic-package mutation. Failure cleans the fresh scope before the global
  modeling-attempt ledger is touched.
- Independent offline testing must execute this command with a clean environment containing only the
  production PATH, not through the backend virtual environment.

### Frozen result-level CQ proof

The v3 authoring contract adds two semantic, not implementation-prescriptive, structures:

- `proof_role_bindings`: stable business/CQ roles bound either to an exact public base role or to one
  principal `client_item_id`; and
- `cq_assertions`: Agent-authored positive or negative RDF edge assertions grouped under the three
  frozen CQ IDs. Assertions refer only to proof roles and state the Agent's own consumer conclusion;
  they do not contain raw SPARQL.

The visible contract lists the minimum business roles needed to establish the bounded fixture:
Start/LLM/C invocation/IF-ELSE/Template/manual-review/Output nodes, passing/failing branches, typed
variables, explicit unknowns, bindings/uses and the existing A/B/C endpoints. It does not prescribe
Class names, relation names, IRIs, command ordering or hidden expected answers.

The deterministic sealer validates role uniqueness and that every principal role points to an existing
principal item while every public role exists in the run manifest. It freezes both structures into the
package hash. After principal apply, the Host derives exact resource IRIs from Modeling Batch outputs
and the public map; unresolved or swapped role identities fail closed.

The Host owns query construction. For each CQ it converts the sealed role assertions into bounded,
ontology-scoped SPARQL over exact IRIs, executes it through the public query route, rejects truncation or
incomplete scope, and evaluates every positive/negative assertion against returned triples. Query
templates, limits, ontology scope, derived proof map, assertion results and result hashes are persisted
in Host-only evidence. The CLI cannot inject replacement CQ text, and query success without assertion
success is not L1 PASS.

The hidden acceptance evaluator compares the Agent-authored assertion outcomes with the frozen business
contract:

- CQ1 must prove the complete typed Start → LLM → C invocation → IF/ELSE → Template → Output → A
  binding path;
- CQ2 must prove passing availability, failing/manual-review absence, missing-score
  `explicit_unknown` routing and no external output;
- CQ3 must prove the quality-contract impact set and exclude an unbound same-name decoy.

The evaluator checks modeled public facts and role-bound topology, not labels alone and not supplied
expected-answer constants. The invalid candidate remains dry-run-only and must violate one sealed
module constraint.

### v3 offline release gate

Before the final attempt, independent testing must prove:

1. exact clean-shell sealing succeeds and a missing interpreter/executable fails during `prepare`,
   before the attempt ledger or Agent launch;
2. v1/v2 packages and any role/assertion/hash tampering fail before principal dry-run;
3. role bindings resolve from real compiler output envelopes;
4. positive, negative, missing-edge, decoy and truncated query fixtures change CQ verdicts as required;
5. the CLI accepts no caller-supplied CQ query file;
6. all existing M7, M1/M6, compiler, Ruff, diff and cleanup regressions remain green.

### Review disposition and L0-first split

Focused plan review returned `REVISE` for the L1 portion of this appendix. The clean-shell executable
sealer direction is accepted, but L1 remains blocked until a later revision:

- uses the real `/api/semantic/...` validation, reasoning and SPARQL routes and parses their actual
  scope/staleness envelopes before principal apply is authorized;
- proves `certain-unavailable` with positive public closure/status/constraint facts rather than RDF
  edge absence; and
- restricts resource roles to compiler commands that produce resource outputs, represents relation
  edges and typed literals without reification, and resolves all roles from the principal dry-run
  receipt before apply.

Per the user's explicit sequencing decision, L0 is now an independent hard gate and is the only
authorized implementation slice:

1. a deterministic Host-side L0 preparer creates a repo-local ignored staging directory without a
   Project, Ontology, Build Session, platform API call, RDF-primary mode or modeling-attempt event;
2. staging contains only an immutable L0 contract, executable Python-3 sealer probe and fixed
   non-business fixture;
3. before handing staging to an Agent, the Host runs the exact executable in a separate clean-shell
   copy with production `PATH`, verifies the canonical receipt and deletes that preflight copy;
4. one fresh `fork_turns=none` Agent reads only the L0 staging and runs the same exact command; it
   performs no ontology reasoning, clarification or platform call;
5. the Host verifies allowed directory membership, immutable-input hashes and the Agent-produced
   receipt, then records durable L0 evidence; and
6. an independent tester repeats the clean-shell and Host verification checks.

The L0 receipt proves model reachability, staged-input readability, writable permitted output,
interpreter/helper execution, canonical hashing and Host handoff. It does not count as an M7 modeling
attempt and cannot authorize L1 by itself. No third modeling attempt may start until L0 is independently
`PASS` and the three L1 High findings above have been resolved by a revised plan and review.

## L1 v3 revision after L0 PASS

The real fresh-Agent L0 probe passed. The single remaining modeling attempt stays blocked until this
revision passes plan review and offline tests.

### Pre-Agent live-route contract probe

`prepare` continues to load the accepted base before Agent launch, but must then exercise the actual
public route and response contracts on that base-only fresh scope:

1. Read the Ontology modeling context and exact Graph Set description.
2. POST `/api/semantic/graph-sets/{graph_set_id}/reasoning-runs` with
   `persist_result_graph=false`, then GET `/api/semantic/reasoning-runs/{run_id}`.
3. POST `/api/semantic/graph-sets/{graph_set_id}/validation-runs` with
   `persist_report_graph=false`, then GET `/api/semantic/validation-runs/{run_id}`.
4. POST `/api/semantic/sparql:query` with `scope_mode=ontologies`, exactly the fresh Ontology ID and
   a bounded base-slice ASK/SELECT probe.

The Host requires successful terminal status, consistent reasoning, conforming base validation,
`scope.status=complete`, one and only one matching Ontology, no excluded Ontology, no truncation,
matching workspace version/source signature/Graph Set and no stale/superseded warning. Raw graph
lists are never supplied by the Agent. Any route, request, response or freshness mismatch deletes the
fresh scope before `modeling_started` or Agent launch.

Offline release uses the real FastAPI app and current Pydantic envelopes with dependency-overridden
repositories/services, not a Fake transport that accepts invented paths. A separate guarded live
base-only route probe is required in `prepare`; it creates no principal semantic content.

### v3 proof grammar

The sealed package contains:

- `resource_roles`: each role resolves either to one exact public-base role or to a principal item
  whose `command_kind` is in the compiler's output-capable create set. For the current allowed
  commands this is `create_class`, `create_relation_type`, `create_shape` or `create_entity`.
- `edge_assertions`: positive RDF triples whose subject is a resource role, whose predicate is either
  a resource role or a canonical absolute/builtin IRI, and whose object is either a resource role or
  an inline typed/language/plain literal.
- optional `closed_snapshot_absence_assertions`: bounded absence checks used only as supplemental
  duplicate/unexpected-edge guards, never as proof of a business negative.
- `cq_claims`: each frozen CQ cites the IDs of positive edge assertions that prove its business
  conclusion. No raw query text is accepted.

`create_relation` items are never resource roles because the real compiler returns empty
`resource_outputs`; their modeled triple is represented by the corresponding edge assertion. Literal
operands do not require reified resources. The sealer checks command output capability, role
uniqueness, public role existence, item ordering and operand grammar without prescribing Agent Class,
Property, relation names or IRIs.

The Agent-visible contract publishes only generic role, assertion and CQ-claim grammar. It does not
publish a required role list, case-to-state mapping, manual-review expectation or hidden answer. The
Agent creates its own semantic roles and positive facts after visible-evidence analysis and
clarification. The Host-only evaluator maps those Agent-authored roles/claims to the frozen answer
contract after sealing.

The visible claim vocabulary may express generic distinctions such as `certain_available`,
`certain_unavailable` and `explicit_unknown`, because the CQ already requires those categories. It
must not state which fixture case belongs to which category. A required business negative must be
supported by at least one positive public fact chosen by the Agent: a state/closure resource edge, a
typed literal fact, or an executable constraint outcome. Missing output edges alone fail CQ2.
`explicit_unknown` likewise requires a positive public resource/fact and is not conflated with
unavailability.

The same-name decoy is not Agent-visible and is not part of the L1 principal package. It remains an
offline evaluator fixture and later L2 mutation. L1 CQ3 only proves the impact path over actually
bound public facts; decoy exclusion is rechecked when the deterministic mutation adds one.

### Dry-run admission before apply

After the principal dry-run returns `attempt_status=validated`, the Host:

1. reads each item result using the real Modeling Batch envelope;
2. resolves every principal `resource_role` only from that dry-run's `resource_outputs`, and every
   public role only from the frozen base map;
3. rejects missing outputs, `create_relation` role targets, ID/IRI swaps, duplicate IRIs and scope
   mismatches;
4. resolves each assertion predicate as either a resource role or a canonical absolute/builtin IRI.
   An absolute predicate is accepted only if the exact predicate occurs in the principal dry-run
   normalized RDF delta; it is never accepted merely because the Agent supplied a string;
5. compiles every positive or supplemental assertion into server-bounded read-only SPARQL using exact
   role IRIs and canonical RDF literal syntax;
6. runs the same parser/bounds validator used by the public scoped-query service without querying
   uncommitted facts; and
7. freezes the role map, query hashes, dry-run workspace and candidate hash.

Only then may the exact principal candidate apply. Apply item outputs must equal dry-run outputs;
otherwise the Host fails before CQ evaluation and records an integrity error. This does not require a
relation item to produce a resource.

### Result-level CQ verification

After apply, the Host submits only its frozen generated queries to
`/api/semantic/sparql:query`. Neither CLI nor `continue_guarded` accepts caller-supplied query text.
Every result must retain the same complete single-Ontology scope, workspace version and source
signature established after apply; truncation, excluded scope, stale warnings or signature drift
fails closed.

Positive assertions must be present in public RDF. Supplemental absence assertions must be absent but
cannot satisfy any required CQ claim. The hidden acceptance contract checks that:

- CQ1 cites a connected positive typed flow from both Start inputs through LLM, C invocation,
  quality result, decision, Template, Output and A binding;
- CQ2 cites positive passing availability, positive manual-review routing, positive
  `certain_unavailable` closure for failing and missing-score cases, and positive
  `explicit_unknown` basis facts;
- CQ3 derives the affected set by traversing the positive role-bound dependency graph and excludes
  resources without a real bound path. The deterministic same-name decoy is introduced only in L2.

The Host records assertion outcomes, exact public proof IRIs, query/result hashes and scope metadata.
Agent claims alone are not evidence; a CQ passes only when its cited positive assertions are returned
from the public ontology-scoped query and the hidden result contract is satisfied. Typed-literal
assertions therefore do not require a predicate resource role or Property reification: the predicate
may be an absolute IRI proven to exist in the dry-run delta, including a property key emitted by
`create_entity.properties`. Resource-role predicates remain supported when the Agent models a
resource-producing relation/property representation.

### Revised release gate

Before the final modeling attempt:

1. real FastAPI route integration tests cover the exact graph-set validation/reasoning and scoped
   SPARQL paths, request schemas, detail reads, complete scope, one Ontology, source signature,
   workspace version and stale/truncated failures;
2. real compiler/Batch envelopes prove output-capable role resolution and
   `create_relation -> resource_outputs={}`;
3. dry-run role resolution and query parsing complete before apply, and apply-output drift fails;
4. a sparse graph with no output edge but no positive unavailable fact fails CQ2;
5. positive unavailable/unknown facts pass through resource, typed-literal or constraint proof;
   an undeclared absolute predicate or one absent from the real dry-run delta fails;
6. one mechanically authored, non-business principal fixture passes the real compiler/Batch
   dry-run-output, role/assertion resolution and query-compilation path; it proves both a
   resource-object edge and a typed-literal edge without exposing an M7 answer template;
7. same-name decoy behavior remains an offline evaluator and L2 mutation check, not an L1
   Agent-visible requirement;
8. CLI and Python entry points reject externally supplied query text; and
9. all existing L0, M7, M1/M6, compiler, cleanup, Ruff, diff and runtime-health checks pass.

## User-approved semantic Judge correction

The user rejected using a fixed program as the final judge of open-ended ontology semantics. This
section supersedes every earlier statement that makes the Host-only evaluator authoritative for CQ
business correctness.

### Responsibility boundary

The deterministic Host remains authoritative only for mechanical facts:

- manifests, seals, candidate hashes and allowed files;
- exact dry-run/apply identity, resource outputs, workspace/lease/scope and duplicate-write safety;
- validation/reasoning terminal status;
- query scoping, completeness, truncation, freshness and source signatures;
- evidence-bundle hashes, Judge citation membership and cleanup.

The Host may reject malformed or incomplete evidence, but it does not decide whether a particular
ontology structure is the correct complete typed path, whether a branch means unavailable, or which
resources belong in the impact set. Producer-authored roles, assertions and claims remain useful
query/evidence hints; they are not acceptance answers. The previous `_evaluate_claims` hidden-answer
mapping is removed from the completion gate.

### Public evidence bundle

After principal apply, invalid-candidate rejection, validation and reasoning, the Host creates an
immutable Judge evidence bundle containing:

- frozen run/scope/package/query hashes and dry-run/apply receipts;
- exact public base resource map and resolved Producer proof roles;
- validation/reasoning results and freshness metadata;
- results of Producer-claim queries, marked explicitly as Producer claims; and
- one complete ontology-scoped public RDF snapshot (`SELECT ?s ?p ?o`) with a server-owned bound above
  the frozen scenario ceiling, exact single-Ontology scope, no truncation/exclusion/stale warning and
  canonical row hashes.

The scenario manifest freezes the exact public source/fixture file set and its hashes before the
Producer starts. Judge staging copies that already-selected set verbatim; neither Producer output nor
the main Agent may change the selection. The scenario also freezes a maximum expected snapshot size
below the semantic SPARQL route's 10,000-row limit. `continue` fails before Judge launch when the
reported total can exceed that ceiling, when the returned row count reaches the bound without an
authoritative complete signal, or when scope/signature/freshness checks do not prove a complete current
snapshot.

The bounded snapshot is evidence, not a platform business read model. It is scenario-local and
generic; the Host does not translate triples into Dify-specific conclusions.

### Fresh L1 Judge

The Host writes a separate Judge-visible directory after the evidence bundle is sealed. It contains:

- the three frozen CQ texts and M1 regression questions;
- selected public source/fixture material;
- the hidden answer and acceptance contracts;
- the immutable public evidence bundle and citation schema; and
- no Producer hidden reasoning, prior answer-shaped model, main-Agent conclusion or historical run.

A fresh `fork_turns=none`, read-only Judge subagent independently answers every CQ with:

- `PASS`, `FAIL` or `INCONCLUSIVE`;
- its interpreted business conclusion;
- exact cited public triple-row hashes and validation/reasoning evidence hashes;
- missing/contradictory evidence; and
- a failure classification when not passing.

The Judge may request additional public read-only queries through the main Agent only when the frozen
snapshot is insufficient; every response is appended to the same evidence bundle and scope-checked by
the Host. The Judge has no platform credentials or platform tools. An additional query is accepted
only through a Host-owned allowlisted read path that rejects updates, service/federation clauses,
cross-scope graph access and an unpaired workspace/source signature. The Host records the canonical
request, response, completeness metadata and hashes as an append-only evidence extension before the
Judge may cite it. It cannot write the platform or change the ontology.

### Finalization and cleanup

Successful `continue` stops at `AWAITING_JUDGE` and keeps the owned scope readable. It checkpoints the
evidence boundary but does not complete or delete the Project.

`finalize` accepts only a Judge verdict file from the paired Judge staging. The Host verifies schema,
all CQ IDs, citation hashes against the public evidence bundle, Judge/run identity and append-only
additional-query evidence. It does not recompute the semantic verdict.

- A Judge `PASS` for every required CQ seals the L1 evidence/verdict and moves the run to
  `AWAITING_L2_CONSUMER`. The Build Session and owned Project remain read-only and queryable only for
  the paired L2 blind Consumer; no further modeling or writes are allowed.
- The paired `complete-consumer` transition accepts the sealed blind-Consumer evidence, verifies
  run/scope/signature identity and public-query completeness, then completes the Build Session and
  cleans the owned Project in `finally`.
- `FAIL` or `INCONCLUSIVE` records the semantic result without converting it into a protocol failure
  and immediately cleans the owned Project in `finally`.
- Invalid/mismatched verdict, `abort-judge`, and any Consumer failure or timeout also terminate and
  clean in `finally`; cleanup-only failure remains terminal `CLEANUP_FAILED`.

If the Judge crashes, times out or otherwise produces no valid verdict, the main Agent invokes the
paired, idempotent `abort-judge` transition. It is valid only from that run's `AWAITING_JUDGE` state,
records the original Judge terminal category and bounded public failure detail, seals all evidence
available at that point, marks the semantic outcome `INCONCLUSIVE`, and cleans the owned Project in
`finally`. Repeating it returns the same terminal receipt without a second cleanup. A cleanup failure
must preserve the Judge failure as the primary cause while setting the stable terminal state
`CLEANUP_FAILED`. `finalize` with a malformed, stale or mismatched verdict follows the same fail-closed
terminal cleanup path; it can never leave the scope indefinitely readable.

Only a valid all-PASS Judge verdict may leave a scope temporarily readable, and only in
`AWAITING_L2_CONSUMER`. A paired, bounded Consumer timeout/abort path must seal the Consumer failure
and clean the scope. Repeating `complete-consumer` or its abort returns the same terminal receipt and
never performs cleanup twice.

The main Agent reviews the Judge reasoning and makes the final delivery decision. The existing
independent requirement tester then verifies the evidence/verdict/citation chain. L2 blind Consumer
remains separate and receives no hidden contract.

### Revised offline gate

Before the final modeling attempt:

1. fixed Host semantic-answer mapping is non-authoritative or removed;
2. complete bounded RDF snapshot success and truncated/partial/stale failures are tested;
3. Judge staging excludes Producer reasoning/history and includes hidden contracts only after Producer
   completion;
4. a fresh-Judge fixture can distinguish complete, missing and contradictory semantic evidence;
5. verdict citation hashes must exist in the evidence bundle, while invented/stale citations fail;
6. `continue -> AWAITING_JUDGE -> finalize` covers PASS, FAIL, INCONCLUSIVE and invalid verdicts:
   PASS alone enters read-only `AWAITING_L2_CONSUMER`, then paired Consumer complete/abort cleans;
   other outcomes clean immediately; paired idempotent `abort-judge` covers Judge
   crash/timeout/no-verdict and cleanup failure;
7. no semantic verdict is hardcoded in Host code or exposed to the Producer; and
8. L0, v3 protocol, M1/M6, compiler, route, cleanup, Ruff and diff regressions remain green.

## Attempt-3 evidence-reference failure and v4 recovery

Attempt 3 reached a semantically complete, helper-sealed Producer package but failed its principal
dry-run before apply. Every Modeling Item carried inline source evidence plus non-empty
`evidence_reference_ids` and `competency_question_ids`. The fresh Project contained no governed
Evidence or Competency Question records with those IDs, so the platform correctly returned
`evidence_not_found` and `competency_question_not_found`. The Host cleaned the owned scope.

This is a scenario Host/Agent authoring-contract defect, not a platform product gap and not a modeling
quality result:

- the visible contract admitted the two reference arrays and described itself as complete;
- neither the deterministic base nor `prepare` created or published governed Evidence/CQ IDs;
- inline `evidence` already preserves source excerpts; and
- scenario-level `cq_claims` already carry the Producer's semantic CQ proof hints for the fresh Judge.

The v4 recovery therefore makes the smallest mechanical correction:

1. `evidence_reference_ids` and `competency_question_ids` must be empty for every principal and invalid
   Modeling Item unless their exact governed IDs appear in a future run manifest; the current run
   manifest publishes none.
2. The sealer rejects non-empty values before publishing a sealed package. Source fidelity remains in
   inline `evidence`; semantic CQ mapping remains in `cq_claims`.
3. Compiler/Host pre-admission tests prove a visible-only Producer package with inline evidence and
   empty governed-reference arrays reaches real principal dry-run admission, while either non-empty
   array fails before platform submission.
4. Historical packages, runtime roots and all three ledger events remain immutable.

Because attempts 1–3 all failed before principal apply on reproduced Runtime/scenario-contract
defects, the user-authorized adaptive ceiling is raised once from three to five. Attempt 4 is the next
fresh L1 run. Attempt 5 is reserved for the required L2 independent modeling repeat and may start only
after attempt 4 reaches an all-PASS Judge verdict. No sixth modeling start is permitted. Consumer and
deterministic mutation runs still do not consume modeling attempts.

This correction and ceiling change require a new plan-review PASS and independent offline PASS before
attempt 4. No platform code change is required.
