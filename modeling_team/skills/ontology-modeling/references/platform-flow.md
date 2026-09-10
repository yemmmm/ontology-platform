# Semantic handoff and returned evidence

Use this reference to decide what Modeling supplies and what evidence it needs back. The selected
Task controls stages, schemas and approvals. This table does not assign platform operations to
Modeling or introduce a universal execution sequence.

| Work | Modeling supplies or decides | Protocol evidence to inspect |
| --- | --- | --- |
| Scope | Source-grounded meaning, proposed scope, gaps and questions | Actual authorized Project/Ontology bindings when needed |
| Candidate | Complete neutral semantic content, evidence and dependencies | Translation receipt or a concrete conflict |
| Constraints | Source-supported Shapes and an intentionally invalid example | Dry-run findings; the negative example remains unapplied |
| Application | Approved semantic revision and answers to semantic conflicts | Applied Batch/Attempt bindings and readback for that revision |
| Validation / reasoning | Interpretation and correction of semantic findings | Validation scope, conforms/findings, consistency/findings |
| Retrieval | Public consumer questions and required semantic relationships | Scoped facts, relations, lineage and explicit completeness |
| Handoff | Own artifacts, outstanding unknowns and semantic findings | Bound execution evidence required by the Task |

Build Session creation, leases, Batch envelopes, request schemas, idempotency and platform calls
belong to Protocol. Do not reconstruct these from a high-level recipe or change business meaning
in response to a purely mechanical translation failure.

## Explicit unknowns

Represent an unresolved business decision through the mounted semantic contract. Where the contract
uses a model-local `kind=explicit_unknown` resource, preserve its stable identity, affected semantic
scope, unanswered business question, source basis and rationale, with no asserted answer value.
Connect it to the affected model meaning so a governed consumer can observe the uncertainty.
Do not create source-row instances or a platform-domain feature to carry the unknown.

## Evidence completeness

Check that returned results refer to the expected candidate/revision and authorized scope. Preserve
asserted versus inferred status, provenance, warnings, pagination and explicit completeness. A
truncated page or missing lineage is not evidence that the complete model supports the answer.

The platform returns facts, topology, provenance and state. The consumer interprets business
answers; Modeling must not claim an independent acceptance result from its own successful query.

## Respond to findings

- Source contradiction or unresolved business meaning: ask the grounded question through the
  declared channel, or preserve an explicit unknown.
- Semantic candidate or Shape finding: correct only the evidenced semantic defect and hand off
  the required complete revision.
- Request-shape, lease, identity-binding or execution failure: return the exact conflict to
  Protocol; do not invent platform mechanics or change the candidate to bypass it.
- Incomplete retrieval: identify the missing scope/path/evidence and request the needed result.
  Do not infer an answer from missing or inaccessible facts.

Authorization, attempt accounting and run lifecycle belong to the Delivery host. Do not start a
replacement modeling session or an acceptance consumer from this role.
