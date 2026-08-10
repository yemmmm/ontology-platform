# Manual-review publication case

The following case is an approved business record for the same C -> B -> A path.

- Content record: `content-review-001`.
- B submitted `content-review-001` to the currently consumed published version of C.
- C completed successfully without a numeric quality value and returned diagnostic code
  `CLASSIFIER_UNAVAILABLE`.
- B created decision record `decision-review-001` for `content-review-001` with outcome
  `manual review required`. B did not automatically retry C and did not report the content as
  publishable.
- A evaluated `decision-review-001` and created outcome record `publication-outcome-review-001`
  with state `held for review`. No published result was created for `content-review-001`.

This record does not state the later result of human review and does not establish a general rule
for numeric scores, thresholds, retry behavior for other diagnostics, or unrelated workflows.
