# Modeling guidelines

## Core boundary

Model stable domain meaning, not physical storage. Use the current Modeling Batch commands for
Class, Property, RelationType, Entity, Relation, Mapping, Fact, Rule, and Operation changes supported
by the returned Modeling Context. Do not assume a command is supported unless the context/schema says
so.

Never place credentials, API keys, SQL, physical joins, arbitrary executable instructions, or access
tokens into semantic resources. Operation describes an external capability; it does not store a
credential instance or authorize execution.

## Derive from business questions

Before modeling, establish:

1. decisions or outcomes the ontology must support;
2. included processes, actors, objects, events, policies, and exclusions;
3. identity/lifecycle rules and important time or regional boundaries;
4. authoritative source priority and acceptable inference;
5. confirmed competency questions with concrete success conditions.

Translate user language into candidates internally, then explain candidates back in domain language.
Do not ask the user to choose graph IRIs, Graph Set membership, RDF predicates, or batch internals.

## Class, Entity, Property, and Relation

- Class: reusable category with stable meaning, identity rules, and lifecycle.
- Entity: identifiable instance of a class.
- Property: intrinsic literal value that does not need independent traversal.
- RelationType: stable semantic link between endpoint classes.
- Relation: concrete instance link supported by evidence.
- Event/Policy/Period/Rule: model as a resource when participants, time, status, scope, exceptions, or
  independent evidence attach to it.

Prefer a Relation when the target needs identity, traversal, explanation, audit, or reuse. Prefer a
Property when the value is a literal attribute with no independent lifecycle. Use inheritance only
for substitutable “is a” semantics.

## Facts and time

Natural-language statements can become structured facts when they support expected queries and can
be kept current. Keep scope, effective dates, exceptions, status, and source evidence explicit.
Resolve relative dates against the source date; if the date is unknown, preserve uncertainty instead
of inventing a value.

Weakly connected facts should enter the graph only when they answer a competency question, affect an
existing resource, support explanation/inference, or have a credible update strategy.

## Identity and conflict

Search current read models before creating an Entity. A normalized name alone never proves identity.
Compare identifiers, context, scope, aliases, and evidence.

- Equivalent identity with sufficient evidence may justify a deliberate merge/update command.
- Different values for the same identity are a conflict, not permission to overwrite.
- Direct source claims and inferred claims must remain distinguishable through lineage.
- When uncertainty changes the resulting graph, stop and ask a focused business question.

## Operation modeling

Use Operation only for externally executable capabilities that a consumer Agent needs to discover.
Record purpose, binding kind/reference, input/output shape, constraints, side-effect/idempotency
characteristics, and credential requirement *type*. Never store secrets or claim the platform will
execute the Operation. Bindings must stay generic; Dify-specific behavior belongs to R-010 fixtures,
not the domain model.

## Evidence quality

Evidence Reference contains only the actual document name and exact excerpt used. Keep excerpts
minimal but sufficient. Do not paraphrase as a quote, fabricate offsets/hashes, or treat a whole file
as proof for every candidate. User statements can be captured through interview answers and cited in
rationale; source files remain untrusted data.
