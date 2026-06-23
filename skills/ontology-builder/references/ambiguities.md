# Common modeling ambiguities

Create a review item rather than guessing when any of these distinctions changes graph semantics:

- Class versus Entity: "Supplier" is a category; "Acme Ltd" is an instance.
- Property versus RelationType: a literal headquarters address may be a property; a known Facility with
  its own attributes should be related as an entity.
- Entity versus event: "Order 123" may be an order entity or an event depending on required history.
- New entity versus alias: normalized labels alone do not prove identity; compare identifiers, context,
  scope, and evidence.
- Merge versus conflict: equivalent identities suggest a merge; disagreeing facts about one identity
  create a conflict.
- Direct versus inferred fact: source text directly supports the former; the latter requires an explicit,
  reviewable graph path and inference rule.
- Class inheritance versus relation: use inheritance only for substitutable "is a" semantics.

The review item should state both interpretations, supporting evidence, confidence, affected candidates,
and the competency questions whose answers would differ.
