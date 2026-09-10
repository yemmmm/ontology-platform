---
name: ontology-model-reviewer
description: DEPRECATED historical candidate-review role. Do not use for new modeling work; use modeling-dev-loop instead.
---

# DEPRECATED: Ontology Model Reviewer

This fixed candidate-review role is retained only as historical evidence. Do not execute its
assignment gate or make it a completion dependency.

Use [`modeling-dev-loop`](../modeling-dev-loop/SKILL.md) and invoke
`$modeling-dev-loop`. Current correctness comes from platform dry-run, executable negative Shape,
validation, reasoning, governed retrieval, and a fresh read-only consumer.

The shared semantic method used inside the Team is
[`ontology-modeling`](../../modeling_team/skills/ontology-modeling/SKILL.md).
