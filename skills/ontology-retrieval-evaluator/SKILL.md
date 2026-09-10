---
name: ontology-retrieval-evaluator
description: DEPRECATED historical retrieval-evaluator role. Do not use for new modeling work; use modeling-dev-loop instead.
---

# DEPRECATED: Ontology Retrieval Evaluator

This fixed evaluator role is retained only as historical evidence. Do not execute its assignment
gate or reuse its role handoff.

Use [`modeling-dev-loop`](../modeling-dev-loop/SKILL.md) and invoke
`$modeling-dev-loop`. When blind verification is required, create a fresh read-only consumer using
the prompt and information boundary defined by the current skill.

The shared semantic method used inside the Team is
[`ontology-modeling`](../../modeling_team/skills/ontology-modeling/SKILL.md).
