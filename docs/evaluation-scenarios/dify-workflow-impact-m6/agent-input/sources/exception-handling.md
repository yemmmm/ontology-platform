# Scoring availability and downstream behavior

C can complete content evaluation without a numeric scoring field when its classifier dependency is
unavailable. In that case C still returns a successful workflow completion and a diagnostic code.

B's operating note says that low-scoring content must not be returned as publishable. It describes
the normal numeric comparison but does not state whether B blocks, continues, retries, or marks the
result for review when the scoring field is absent. A publishes whatever B reports as publishable.
