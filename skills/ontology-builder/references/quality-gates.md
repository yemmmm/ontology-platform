# Quality Gates

All six pre-apply gates must pass before the main Agent writes. The seventh gate passes only after
persisted verification.

## 1. Business gate

Goal, scope, non-goals, high-priority competency questions, and success conditions are confirmed,
or the user explicitly accepts identified uncertainty.

## 2. Semantic gate

Identity, lifecycle, relation meaning, key terms, and material conflicts have no untreated blocking
ambiguity.

## 3. Coverage gate

Every important knowledge item has an explicit Coverage Matrix status, and the vertical slice can
support the target competency questions. Deferred/missing content stays visible.

## 4. Evidence gate

Important model elements have exact Evidence References. Unsupported claims remain explicitly
unsupported; do not fabricate evidence.

## 5. Platform gate

The exact Modeling Batch draft has a current dry-run. Every deterministic Finding is fixed or has
an explicit accepted disposition. Use the Attempt ID plus `finding_fingerprint`, never code/path
alone.

## 6. Independent review gate

The reviewer saw original source inventory/key evidence, Pack/Matrix, draft, and dry-run Findings.
Only `PASS` opens apply. `REVISE` creates new immutable draft/review versions and a rework event;
`BLOCKED` stops until evidence or clarification changes.

## 7. Verification gate

After apply, current read model, Context Query/SPARQL, validation, and lineage demonstrate the
target competency questions and evidence traceability. Persist the verification report and event.
Platform validation alone cannot pass this gate.

## Review and rework

- Keep every failed review and rework round; never overwrite it.
- Categorize omissions, term/identity/relation/granularity errors, evidence gaps, competency
  question gaps, over-modeling, stale knowledge, or other issues using the exact platform enum in
  [workflow-artifacts.md](workflow-artifacts.md), not prose aliases such as `omission`,
  `evidence_gap`, `independent_reviewer`, or `blocking`.
- Record introduced/detected phases, detecting role, severity, actual rework cost when known, and
  earliest preventable phase. Root cause is unknown or a clearly labeled hypothesis.
- Re-run dry-run and independent review whenever the batch's semantic content changes.
- Do not acquire a lease before gates 1-6 pass.
