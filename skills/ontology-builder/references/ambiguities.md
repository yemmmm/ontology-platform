# Common modeling ambiguities

Stop for a focused clarification rather than guessing when any distinction changes graph semantics:

- Class versus Entity: "Supplier" is a category; "Acme Ltd" is an instance.
- Ontology versus database schema: "student_table" is a storage object; "Student" is a domain concept.
- Property versus RelationType: a literal headquarters address may be a property; a known Facility with
  its own attributes should be related as an entity.
- Entity versus event: "Order 123" may be an order entity or an event depending on required history.
- Schema relation versus entity relation: `CourseOffering CONFLICTS_WITH CourseOffering` may be schema;
  two concrete course offerings conflicting is an instance fact.
- Domain fact versus source field: "dormitory curfew is 23:00" may be an `AccessPolicy`; an ID card
  database column is storage metadata and is not a domain fact.
- Knowledge graph versus document store: weakly related facts enter the graph only when they support
  expected queries, affect existing entities, or can be kept fresh.
- New entity versus alias: normalized labels alone do not prove identity; compare identifiers, context,
  scope, and evidence.
- Merge versus conflict: equivalent identities suggest a merge; disagreeing facts about one identity
  create a conflict.
- Direct versus inferred fact: source text directly supports the former; the latter requires an explicit,
  reviewable graph path and inference rule.
- Class inheritance versus relation: use inheritance only for substitutable "is a" semantics.
- Operation versus ordinary resource: an executable capability with an external binding is an
  Operation; a policy, procedure description, or credential instance is not.

The clarification should state both interpretations, supporting evidence, confidence, affected
candidates, and which competency-question answers would differ. Record the decision in the next
checkpoint and item rationale; do not fabricate a platform review queue.
