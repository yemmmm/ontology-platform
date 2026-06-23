# Modeling guidelines

- Use a Class for a reusable category and an Entity for an identifiable instance.
- Use a Property for an intrinsic or literal value; use a RelationType when both endpoints have identity,
  independent evidence, or traversal value.
- Model events as Classes when participants, time, state, or provenance must attach to the event.
- Prefer the narrowest stable concept that answers approved competency questions. Avoid speculative
  abstractions with no source or question.
- Give every class a description, aliases, parent references, and evidence.
- Give every property a domain class, value type, required/multi-value flags, enum values, and constraints.
- Give every relation a source Class, target Class, inverse name when meaningful, and optional parent.
- Do not create inheritance cycles, cross-ontology parents, invalid domain/range endpoints, or duplicate
  normalized names.
- Preserve source language labels as aliases when choosing a canonical name.
- Represent uncertainty in confidence and review status, not by weakening deterministic constraints.

Minimum schema usability for broad extraction means at least one reviewed Class for every extracted
entity kind, reviewed RelationTypes for proposed edges, and no blocking schema validation errors.
