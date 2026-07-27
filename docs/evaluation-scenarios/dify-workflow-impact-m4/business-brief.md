# Dify Workflow-as-Tool M4 business brief

This is a bounded C -> B -> A business slice. C scores content, B generates content by invoking C,
and A publishes B. C has a Current Draft and published Versions; do not conflate those states.

The documented source material establishes the three workflow identities, their C -> B -> A path,
and the distinction between Current Draft and Latest Version. It does **not** settle all of the
following consequential business semantics:

- Does B invoke C through C's Latest published Version, or through an earlier published Version?
- Is `quality_rating:number` the successor of `quality_score:number`, or is it a separate contract
  change?
- When score data is unavailable, is B's behavior confirmed by the business owner?

The model must preserve a material unresolved answer as an explicit gap. Do not infer a fallback,
an absence, or a relationship merely because the brief is silent. Source excerpts remain Evidence;
clarification answers are user-confirmed business decisions and belong in the modeling rationale.

The acceptance consumer must be able to observe the current C target and contract used by B, output
continuity or its positive discontinuity facts, and the unresolved missing-score gap through the
normal governed semantic query path.
