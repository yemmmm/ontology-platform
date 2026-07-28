# Modeling task

Build a small, reusable semantic model for the supplied Workflow-as-Tool business materials.

Before creating the principal schema, assess whether the supplied documents uniquely determine the
terms, identities, lifecycle relationships, constraints, and answers required by the consumer
questions. When a missing business decision would change the model or a consumer answer, ask one
plain business question at a time, cite the relevant documents, and explain the affected conclusion.
Do not ask the user to design Classes, Properties, Shapes, IRIs, or Batch payloads.

Do not treat silence as a default. An answer that cannot be confirmed must become a named explicit
unknown in the applied model.

You may read only files under this `agent-input` directory and results returned by platform tools
during this attempt. Do not search or read the repository, prior runs, requirements, test plans,
hidden contracts, memories, or other agents' work.

The Host supplies empty Project and Ontology IDs. Create a fresh Build Session and perform all
modeling yourself using the existing ontology-platform MCP: immutable Modeling Batch dry-run/apply,
an executable Shape with a rejected negative example, valid instance application, validation,
reasoning, a governed semantic query, checkpoint, and completion. Preserve each clarified decision
or explicit unknown in model rationale and public semantic facts.
