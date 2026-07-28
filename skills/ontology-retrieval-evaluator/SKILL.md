---
name: ontology-retrieval-evaluator
description: DEPRECATED historical retrieval-evaluator role. Do not use for new modeling work; use ontology-modeling instead.
---

# DEPRECATED: Ontology Retrieval Evaluator

This fixed evaluator role is retained only as historical evidence. Do not execute its assignment
gate or reuse its role handoff.

Use [`../ontology-modeling/SKILL.md`](../ontology-modeling/SKILL.md) and invoke
`$ontology-modeling`. When blind verification is required, create a fresh read-only consumer using
the prompt and information boundary defined by the current skill.
