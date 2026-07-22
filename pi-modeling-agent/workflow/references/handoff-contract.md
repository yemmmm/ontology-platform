# Structured Handoff Contract

Roles never share hidden conversation, full transcripts, hidden reasoning, raw platform responses,
credentials, or lease tokens. Every handoff uses structured artifacts and stable locators in the
Shared Modeling Directory.

## Allowed handoff payload

- role name, run id, stage;
- stable locators (`brief_path`, `coverage_path`, `candidate_path`, `result_path`, ...);
- candidate hash, review verdict, bounded findings with affected locators;
- bounded user answers or Findings relevant to the task.

## Forbidden handoff payload

- another role's hidden chat or reasoning;
- full prompts or transcripts;
- raw source bodies or raw platform responses;
- credentials, API keys, or lease tokens;
- unneeded Batch content or unrelated Work Unit results.

## Boundary rules

- A path that resolves outside the current run root fails closed.
- A `work_unit_id` that differs from the assigned unit fails closed.
- A candidate whose hash does not match the bound hash fails closed before content review.
- The model never receives an unrestricted generic platform write tool; protected writes are requested
  through `submit_platform_action` and executed by the Runner after one-shot authorization.
