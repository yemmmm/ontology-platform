# Content scoring and publication policy supplement

This supplement applies to the same C -> B -> A Workflow-as-Tool path described by the
existing workflow landscape and release register.

## Output continuity

Workflow C Version 1 exposed `quality_score:number`. Version 2 renamed that output to
`quality_rating:number` to align the interface with current business terminology. Both fields
represent the same business measure: the content quality evaluation produced by C.

The rename did not change the measure, numeric range, unit, calculation, or interpretation.
When a numeric value is present, values from the two fields are business-compatible and may be
compared across Version 1 and Version 2. Integrations must still use the field name published by
the release they consume; the two names are not interchangeable within one release payload.

## Missing-score decision

When C completes without a numeric score because its classifier dependency is unavailable, C
returns diagnostic code `CLASSIFIER_UNAVAILABLE`.

For that result, B must not classify the content as publishable and must not automatically retry
C. B records a `manual review required` publishability decision and returns that decision with the
content result. This rule is specific to the absent-score result with diagnostic code
`CLASSIFIER_UNAVAILABLE`; it does not define how B handles an ordinary numeric score.

A publishes content only when B reports an explicit `publishable` decision. When B reports
`manual review required`, A holds the content for review and does not create a published result.
The later human-review process and its eventual decision are outside this supplement.
