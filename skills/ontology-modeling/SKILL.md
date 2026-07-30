---
name: ontology-modeling
description: Build or update an evidence-grounded ontology by discovering consequential semantic gaps, clarifying them in business language, applying the model through deterministic platform validation, and proving that a fresh consumer can retrieve the intended meaning. Use for ontology modeling from business sources, semantic-gap discovery, modeling-quality experiments, formal application, or blind-consumer verification.
---

# Ontology Modeling

Use one Modeling Agent to own source interpretation, clarification, semantic design, and every
modeling payload. Use the platform for deterministic validation, persistence, provenance,
governance, and retrieval. Do not insert a role Harness between them.

## Team Profile execution boundary

This Skill has one semantic method, but the selected Profile determines who executes platform
requests. When the frozen Profile has a distinct Protocol Agent, the Modeling Agent owns all
business interpretation and the complete semantic payload, then sends that payload unchanged to
Protocol. Protocol alone performs public platform/MCP calls and returns exact platform results.
The Modeling Agent must not call platform tools in that Profile.

When one Agent legitimately holds both Modeling and Protocol responsibilities, it may follow the
standalone end-to-end flow below. This boundary does not add Runner, roster, dispatch, Runtime, or
candidate-approval mechanics to the Skill.

## Establish the contract

1. Read the authoritative requirement and only the declared business sources. In
   `ontology-platform`, read the relevant entry in `docs/requirements/requirements-v1.0.md` or the
   active versioned requirement before changing platform behavior.
2. State the modeling scope, declared sources, consumer questions, available platform interface,
   and any explicit attempt budget.
3. Keep business concepts in ontology data. Do not add domain-specific platform routes, fields, or
   inference rules to make one scenario pass.
4. Keep future productization out of a modeling-quality experiment unless it protects modeling or
   retrieval correctness.
5. Supply the modeling Agent with either registered typed tools or the current public API contract
   needed for every allowed request. An isolated Agent must never guess a method, path, or payload
   schema.

For an evaluation, freeze an Agent-visible input directory and its hashes. Give a fresh modeling
subagent only that directory, empty scope identifiers, and results returned during its own run.
Use `fork_turns=none`; do not pass conversation history, hidden answers, test contracts, prior model
payloads, memories, or another Agent's work.

## Discover semantic gaps before modeling

Before creating the principal schema, decide whether the visible evidence uniquely determines:

- canonical terms and distinctions;
- entity identity and version identity;
- lifecycle, succession, and temporal meaning;
- relation direction, cardinality, ordering, and scope;
- constraints and invalid states;
- answers required by the consumer questions.

Identify material gaps yourself. Do not rely on a prewritten question list, question count, or
category names.

Ask one consequential business question at a time. Cite the visible evidence or tension, explain
which model or consumer conclusion changes, and wait for the answer before asking the next question.
Do not ask the user to design Classes, Properties, Shapes, IRIs, or Batch payloads. Do not repeat an
explicit fact or ask generic questionnaire items.

If the answer cannot be confirmed, preserve a named, queryable model resource with
`kind=explicit_unknown`, a stable identifier, the affected subject/scope, the unanswered business
question, source evidence, and rationale. Assert no answer value. Define and validate this
model-local representation in the schema so a generic semantic query and a fresh consumer can
recover it. Never convert silence, uncertainty, or missing evidence into a default.

Use the modeling and Host prompt patterns in [references/prompts.md](references/prompts.md).

## Build through the platform

Follow [references/platform-flow.md](references/platform-flow.md):

1. Let the Host create only an empty Project and Ontology when credentials or scope creation are not
   available to the modeling Agent.
2. Create and own a fresh Build Session.
3. Submit the schema, vocabulary, constraints, and rationale through immutable Modeling Batch
   dry-run and apply.
4. Prove at least one important executable Shape with a negative instance that is rejected and not
   applied.
5. Submit valid instances through dry-run and apply. Make at most one narrow,
   validation-evidence-driven correction per defect; do not silently redesign the model.
6. Run validation and reasoning.
7. Run a governed, scoped, complete semantic query that exercises the consumer questions.
8. Save the checkpoint and complete the Build Session only after the evidence is coherent.

Prefer registered platform tools or MCP. If the available interface is read-only, the Host must first
provide the current public OpenAPI fragments or equivalent request schemas for the allowed
operations as declared Agent-visible input. Then emit exactly one request at a time as
`{method, path, body}`. The Host may attach the base URL and credentials, forward the request
unchanged, and return the exact status and result. The Host must not write, repair, reorder,
synthesize, or retry semantic content. Stop as blocked instead of guessing when the supplied
contract is missing or inconsistent.

## Verify with a fresh consumer

Give a fresh read-only consumer only the public scope identifiers, generic query contract, and public
platform results. Do not provide the sources, clarification transcript, hidden expectations, model
payload, or prior conversation.

Require the consumer to answer the declared questions from observed facts, preserve provenance and
warnings, distinguish asserted from inferred facts, report incomplete/truncated results, and keep
unknowns unknown. Treat a plausible answer without retrievable evidence as failure.

## Control attempts

Apply an attempt limit only when the user or evaluation contract sets one. One modeling attempt is
one fresh modeling Agent, fresh input workspace, fresh Project/Ontology, and fresh Build Session.
The Host owns an append-only JSONL ledger outside the frozen Agent-visible input. Append one
`modeling_started` record before launch and one terminal `modeling_completed` or `modeling_blocked`
record afterward; include `attempt`, timestamp, fresh scope identifiers, subagent identifier, and
evidence locator. Never store hidden answers or credentials in the ledger and never reuse a
deprecated Harness ledger. Tester, reviewer, blind-consumer, and same-run mechanical repairs are not
new modeling attempts.

When the configured limit is reached, stop modeling, preserve the evidence, and report the current
state. Do not increase the limit or launch another modeler to tune the result.

## Completion gate

Report completion only when:

- every modeled claim is grounded in a declared source, confirmed answer, or explicit unknown;
- material gaps were discovered without leaking the expected question set;
- the applied schema and instances came from Agent-authored immutable Batch payloads;
- an important negative example was rejected by an executable Shape;
- validation conforms and reasoning is consistent, or every remaining finding is explicit;
- a complete scoped query supports the consumer questions;
- a fresh consumer recovers the intended conclusions without guessing;
- the Host did not perform semantic work;
- the attempt count and stable semantic identifiers are recorded.

Do not invoke any artifact listed in
[references/deprecated-artifacts.md](references/deprecated-artifacts.md). They are historical
evidence, not dependencies of this workflow.
