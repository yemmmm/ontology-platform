---
name: ontology-modeling
description: Build or update source-grounded ontologies, clarify consequential business gaps, and verify applied semantics through governed retrieval. Use for semantic modeling and modeling-quality experiments, not ordinary platform code edits.
---

# Ontology Modeling

The Modeling role owns source interpretation, clarification, semantic design, and semantic
payloads. The platform owns deterministic validation, persistence, provenance, governance, and
retrieval. Follow the selected requirement and Profile for role allocation; a standalone Agent
may hold multiple responsibilities. Do not reactivate the deprecated role Harness.

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

1. The Delivery Agent identifies the owning entry in `docs/requirements/` and reads only its
   applicable base/related links. No historical version is the default. An isolated Modeling
   Agent follows the supplied task and declared sources, without opening repository requirements.
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

Ask one consequential business question at a time. Cite the visible evidence or tension and explain
which model or consumer conclusion changes. Wait before asserting the dependent meaning, while
continuing independent analysis. Use an already confirmed answer without asking it again.
Do not ask the user to design Classes, Properties, Shapes, IRIs, or Batch payloads. Do not repeat an
explicit fact or ask generic questionnaire items.

If the answer cannot be confirmed, preserve a queryable `kind=explicit_unknown` using the
representation in [platform-flow.md](references/platform-flow.md). Never convert silence,
uncertainty, or missing evidence into an asserted answer.

Use the modeling and Host prompt patterns in [references/prompts.md](references/prompts.md).

## Build through the platform

Follow the evidence sequence in [references/platform-flow.md](references/platform-flow.md), with
the selected task's stages and role ownership. Use immutable Modeling Batch dry-run/apply, prove
an important Shape rejects an unapplied negative example, and verify validation, reasoning, and
governed retrieval before closure. For relational scenarios, instances are semantic resources;
business rows remain in the source database. Correct evidenced defects and retry safely in the
same run. Do not silently redesign the model; uncertain writes require state inspection first.

Prefer registered platform tools or MCP. If the available interface is read-only, the Host must first
provide the current public OpenAPI fragments or equivalent request schemas for the allowed
operations as declared Agent-visible input. Then emit exactly one request at a time as
`{method, path, body}`. The Host may attach the base URL and credentials, forward the request
unchanged, and return the exact status and result. The Host must not write, repair, reorder,
synthesize, or retry semantic content. If the supplied contract is missing or inconsistent, report
the exact missing operation/field and request corrected input. Suspend that operation without
guessing; resume the same run when the contract is repaired and state is safe.

## Verify with a fresh consumer

Give a fresh read-only consumer only the public scope identifiers, generic query contract, and public
platform results. Do not provide the sources, clarification transcript, hidden expectations, model
payload, or prior conversation.

Require the consumer to answer the declared questions from observed facts, preserve provenance and
warnings, distinguish asserted from inferred facts, report incomplete/truncated results, and keep
unknowns unknown. Treat a plausible answer without retrievable evidence as failure.

## Control attempts

Use the current user authorization and repository default (three fresh semantic starts per
authorization unless specified otherwise). This skill does not authorize a start. A fresh semantic
modeling start consumes one attempt; scope freshness follows the selected new-scope or existing-scope
task, rather than requiring every attempt to create a Project/Ontology.
The Delivery Agent records starts, terminal state, identifiers, and evidence in the existing run
ledger as described in platform-flow.md. Tester, reviewer, blind-consumer, and same-run mechanical
repairs are not new modeling attempts.

When the configured limit is reached, stop modeling, preserve the evidence, and report the current
state. Do not increase the limit or launch another modeler to tune the result.

## Semantic acceptance evidence

Apply the selected acceptance stage. Mechanical verification is not final semantic acceptance;
later repeatability/productization stages do not block an earlier stage. Final semantic acceptance
requires:

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
