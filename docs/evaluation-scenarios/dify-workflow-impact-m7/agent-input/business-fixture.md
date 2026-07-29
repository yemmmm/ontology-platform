# Synthetic fixture: Content Generation Workflow B

This is a `synthetic-fixture`, not an official Dify product statement. B accepts `topic:string` and
`channel:string` at Start, produces `draft_content:string` in an LLM node, invokes C Version 2 and
receives `quality_rating:number`, then evaluates a condition. Its passing branch reaches a Template
that produces `publishable_content:string`; its failing branch reaches manual review. B has an Output
named `approved_content:string`, and A has a `publish_content` binding from B.

The accepted base slice already establishes B-to-C and A-to-B invocation topology, the continuity of
`quality_score` to `quality_rating`, and an explicit unknown for a missing score. It does not tell you
whether the failing branch produces an external output, whether the Template and Output variables are
the same identity or explicitly bound, or how a missing score is routed. Ask only if the answer changes
the model or a consumer conclusion.
