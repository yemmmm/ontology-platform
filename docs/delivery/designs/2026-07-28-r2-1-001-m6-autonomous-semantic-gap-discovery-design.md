# R2.1-001 M6 建模 Agent 自主业务语义缺口发现执行设计

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M6
- Delivery record:
  `docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-28-r2-1-001-m6-autonomous-semantic-gap-discovery-test-plan.md`
- Status: implemented — one modeling attempt completed; independent test PASS
- Scope version: M6 contract v3

## Goal

Prove that a fresh modeling Agent can decide which consequential business questions must be asked from
raw source material, without being told the question list, count or categories, and then complete the
accepted clarification-to-model workflow.

M6 complements rather than replaces M4. M4 proves that an enumerated set of gaps can be clarified and
turned into validated model behavior. M6 proves that the Agent can discover those gaps through source
completeness and consistency analysis.

## Current minimal scope

M6 reuses the bounded Dify Workflow-as-Tool `C -> B -> A` slice and M4's accepted semantic contract.
It does not invoke or import M4's `run_m4_clarification.py`: that runner freezes the explicit-gap M4
manifest/prompt and launches a separate bwrap Codex process, which conflicts with this collaboration
subagent experiment. M6 changes only the Agent-visible source pack, collaboration transport and
discovery acceptance:

- replace the explicit ambiguity list with separate realistic business documents;
- preserve discoverable evidence tensions around invocation version binding, output-contract identity
  and missing-score behavior;
- provide business modeling objectives and consumer outcomes, not an uncertainty checklist;
- retain the generic instruction to check whether source material uniquely determines the model;
- use one fresh discovery Producer and one fresh blind read-only Consumer;
- preserve M4's serial clarification, explicit-unknown, Modeling Batch, SHACL, reasoning and query gates.

The modeling Runtime is a fresh Codex subagent started without parent-turn context. M6 does not require
Pi and may run in parallel with M5 because it validates the modeling method rather than Pi compatibility.
At most three modeling-subagent attempts may be launched. Each attempt uses a new run root and fresh
platform resources; after the third attempt, execution stops and the current evidence is reported even
when M6 has not passed.

## Minimal collaboration adapter

The M6 scenario package contains only:

- separate raw business documents and generic modeling/consumer objectives;
- a frozen manifest plus a deterministic checker for the declared Agent-visible file set and hashes;
- a host-only material-gap/answer contract and discoverability mapping;
- an append-only attempt ledger and focused static/acceptance tests.

There is no M6 model proxy, bwrap launcher, new Runtime or new backend API. The main agent launches the
modeling subagent with `fork_turns=none`; the initial handoff contains only the declared Agent-visible
files, empty scope IDs, the prohibition on reading outside the input pack, the generic requirement to
ask one material business question at a time, and the public platform-call contract. Platform
credentials are not present in the handoff or staged files.

When the subagent sends one source-grounded question, the main agent evaluates it against the host-only
contract, appends request/response hashes and eligibility to the attempt ledger, and sends back only that
question's business answer or explicit uncertainty. A follow-up turn resumes the same subagent. The next
question is not answered until the prior one is bound to a changed assumption or named explicit gap.
Question evaluation never returns category names, remaining count, expected wording or ontology design.

Before launch, the Host uses the existing public HTTP API to create one empty fresh Project and one
empty fresh Ontology because the current MCP surface does not expose Project/Ontology creation. The
Host records and passes only their IDs; it creates no class, property, relation, Shape, entity, fact or
decision.

Live preflight found that the collaboration subagent's connected MCP inventory contained only
read-only tools and could not mutate the fresh scope. M6 therefore uses the smallest credential
adapter: the subagent writes exactly one `{method, path, body}` public HTTP request at a time to its
run-owned request file; the Host attaches only the API credential, forwards that request unchanged and
returns the exact status/result. The subagent still creates its own Build Session and chooses every
lease, Modeling Batch, validation, reasoning, query, checkpoint and completion call and payload. The
Host may not synthesize, alter, retry or repair semantic content. This adapter is a collaboration
transport, not the M4 runner, a model proxy or platform feature.

The main agent/tester may inspect public results and run read-only acceptance queries but must not
repair or complete the model on the subagent's behalf.

This stage does not introduce a second business module, generalized interview product, persistent
question store, Coverage/Work Unit framework, new backend API, or new platform security system.

## Agent-visible inputs

The staged input pack contains only:

1. source documents describing the `C -> B -> A` workflows and invocation path;
2. version/publication material that exposes multiple C states or versions without deciding B's binding;
3. old and new interface material that uses `quality_score` and `quality_rating` without declaring their
   identity or continuity;
4. scoring availability and downstream-use material that makes missing scores possible but leaves B's
   behavior unresolved;
5. business modeling objectives and competency/consumer questions;
6. the generic platform and clarification transport contracts.

No file may say that there are three gaps, name the three decision categories, contain the M4 ambiguity
list, prescribe the expected questions, or expose a hidden answer/model/query result.

## Discoverability rule

The test is not a hidden-fact guessing exercise. Before launch, the independent tester must prove that
each material gap has:

- at least two visible source statements whose combination exposes an unresolved dependency, identity
  or behavior; or
- one visible source statement plus a required consumer outcome that cannot be modeled uniquely without
  the missing decision.

An arbitrary omitted fact with no visible consequence cannot be part of the required hidden material-gap
contract.

## Discovery and clarification behavior

Before schema modeling, the Agent records a source-completeness assessment in its own words. It asks one
business question at a time only when the missing decision changes a modeled boundary, identity,
lifecycle, constraint or required consumer result.

Acceptance is semantic:

- wording and order may differ;
- the Agent is not required to predict the evaluator's labels;
- an extra question is allowed when it cites visible sources and materially affects the model;
- generic questionnaires, exhaustive question dumping, repeated explicit facts and requests for RDF
  design do not satisfy discovery;
- an unanswered material question becomes an explicit named gap rather than a default.

The host may match natural questions to the hidden business-answer contract, but the Agent-visible
handoff and files cannot expose matcher tokens, category names or expected count.

## Formal modeling and consumption

After the required decisions are answered or explicitly uncertain, the Agent follows the M4 formal path:

1. receive the IDs of the Host-created empty fresh Project/Ontology and create its own Build Session
   through the exact credential relay;
2. dry-run and atomically apply the Shape-containing schema;
3. demonstrate rejection of an invalid instance;
4. dry-run and apply its candidate ABox, using at most one SHACL-finding-driven ABox correction;
5. run validation, reasoning and a governed semantic query;
6. checkpoint and complete the Build Session; and
7. let a fresh blind Consumer discover the public semantic read models and report the target contract,
   continuity/discontinuity and explicit unknown gap.

The host/tester chooses neither the ontology structure nor any Batch or lifecycle payload.

## Isolation

The M6 Agent cannot access M4/M5 source packs, prompts containing explicit gaps, hidden answer contracts,
final ontology, Batch payloads, run roots, transcripts, decision logs or acceptance query results. Each
live run uses fresh platform resources, Agent state and a new run root. Failed runs remain evidence and
are never retried in the same workspace.

The subagent is launched with no inherited conversation turns. Its handoff names only the isolated
Agent-visible directory and permitted platform/clarification interfaces. The host records the exact
handoff and the declared files. The subagent must not search or read outside that directory. This is a
contract-level isolation check rather than a new OS sandbox: acceptance requires review of its reported
inputs and actions, and any use of repository paths or undeclared facts fails that attempt.

Plan review, scenario implementation and independent testing subagents do not consume the three-attempt
budget unless they themselves perform the business modeling operation. A blind read-only Consumer also
does not consume it because it cannot mutate the model.

## Acceptance

M6 passes only when independent testing proves:

- every required material gap was discoverable from visible evidence and autonomously identified;
- no visible input disclosed its count, category or expected question;
- questions were source-grounded and material rather than a generic barrage;
- answers and uncertainty changed the applied model and public consumer conclusions;
- M4's formal validation, correction, reasoning, query and read-only boundaries remained intact; and
- no Dify-specific platform behavior or productized interview framework was added.

The original module-expansion milestone is M7 and remains out of this design.
