# Modeling task

Extend the supplied accepted base slice with the bounded Content Generation Workflow module. Read only
the files in this directory and platform results returned during this attempt. Do not search the
repository, historical runs, requirements, test plans, hidden contracts, or other agents' work.

First assess whether the visible materials uniquely determine business identities, typed variable flow,
branch-local availability and consumer conclusions. Ask no more than five material business questions,
one at a time. Each question must cite visible evidence and say what model or consumer conclusion it
changes. Do not ask for implementation choices such as Classes, IRIs, Shapes, or Batch payloads.

Create authoring content only in the single `semantic-package.json` in this directory. Before writing,
read `authoring-contract.json` and the run-specific `run-manifest.json`; they are the complete,
machine-readable Modeling Item and envelope contract. Reuse the public base map exactly when a base
identity is needed; each published role carries both `resource_id` and `resource_iri`, and command
fields must use the declared representation. Do not rely on Host conversion. Include one
agent-authored invalid candidate that violates a module constraint. Preserve unknown business behavior
as an explicit unknown rather than selecting a default.

The initial file must contain exactly the six fields declared by `authoring-contract.json`: principal,
invalid candidate, generic resource roles, positive edge assertions, optional closed-snapshot absence
guards and CQ claims. Each candidate contains an `items` array. Do not add raw query text. Then, from
this directory, run exactly:

```bash
./seal_semantic_package.py --agent-visible .
```

The helper atomically normalizes required Modeling Item metadata and supplies all envelope metadata,
candidate hashes and the sealing receipt. You must run it after every package edit. Do not hand-calculate
or write any SHA-256, run-manifest metadata, public bindings or seal fields. Do not create any output
outside `semantic-package.json` and the permitted `clarifications.jsonl`.

This run manifest publishes no governed Evidence IDs or CompetencyQuestion IDs. Therefore every
principal and invalid Modeling Item must set both `evidence_reference_ids` and
`competency_question_ids` to exact empty arrays. Do not omit, replace, or populate them: the sealer
will reject non-empty values rather than changing them. Put source excerpts in each item's inline
`evidence` entries, and put scenario CQ semantics and role bindings only in the top-level `cq_claims`.
