# R2.3-005 Three-Start Budget Extension Plan

## Outcome

Represent the user's 2026-08-04 authorization as one append-only R2.3-005 `+3` budget tranche, while
preserving the consumed start, all retained evidence, and the historical R2.3-002 exact `+2` contract.
This plan changes deterministic ledger management only; it does not itself launch a Producer or spend
a semantic start.

## Frozen contract

- R2.3-005: `.r2-3-005-start-ledger.jsonl`, `.r2-3-005-start-ledger.lock`, requirement ID
  `R2.3-005`, initial cap 1, exact authorization increment 3.
- R2.3-002: existing filenames, requirement ID, initial cap 2 and exact increment 2 remain unchanged.
- One user authorization appends one record with the existing fields
  `event, additional_starts, authorization_id, reference`; replay is ordered and append-only.
- Current state after authorization is cap 4, one semantic start, three remaining, zero active
  reservations. Budget does not bypass terminal-failure or repair-baseline gates.
- Runs are serial; first accepted PASS stops. A complete modeling-quality result stops further retries.

## Implementation

1. Add one immutable requirement-specific ledger configuration/resolver used by both Runner and CLI.
   It accepts only the two known requirement IDs and supplies exact filenames, lock, initial cap and
   authorization increment. The three management commands expose `--requirement-id`: omission keeps
   the legacy R2.3-002 behavior and formal R2.3-005 use is explicit. Reject unknown IDs, filename/root
   overrides and configuration mismatch before opening or creating a file.
2. Replace the global authorization-increment assumption inside `StartLedger` with the configured
   exact increment. Validate it in constructor, `authorize_budget` and `_start_cap`; keep the default
   R2.3-002 behavior byte-compatible.
3. Make the formal Runner use the same canonical repository ledger root and reject an alternate
   caller-supplied `ledger_root` before file access. Deterministic tests obtain temporary ledgers only
   through an injected resolver/factory seam; eliminate duplicated inline identity data.
4. Enforce the R2.3-005 management sequence under the ledger lock: the latest real semantic start
   must receive a retryable incomplete `terminal_failure`; the exhausted-cap `+3`
   `budget_authorization` must immediately follow that failure; and the first
   `repair_authorization` must immediately follow that budget and bind the exact next baseline. Keep
   one controlled exception for presemantic rebind: after exactly one fresh reservation consumes the
   prior repair, never reaches `semantic_start`, has `presemantic_release`, and leaves no active
   reservation, allow one non-empty different baseline repair for the same semantic-failed run with
   no new budget. Concurrent rebind allows one winner. A valid failure/budget prefix is resumable only
   by its exact next event and cannot reserve a start. Preserve legacy R2.3-002 event semantics.
5. Add R2.3-005 temporary-ledger tests for cap 1 -> 4, malformed/early/duplicate/concurrent
   authorization, replay validation, wrong-ledger isolation, presemantic release, retryable failure,
   complete-modeling-quality refusal, wrong order/run, interrupted-prefix resume, canonical-root
   rejection and exact repair baseline. Test the positive presemantic rebind and rejection of unused
   repair, active/unreleased or semantic-started reservation, wrong failed run, blank/equal baseline,
   duplicate and concurrent rebind. Exercise concurrent contenders at every management event and
   re-run existing R2.3-002 budget tests unchanged.
6. Run focused ledger/CLI tests, all R2.3-005 tests, full `modeling_team` discovery, Ruff,
   `git diff --check`, and GitNexus `detect_changes(compare main)`. Do not touch live ledgers or run
   roots in development/testing.
7. After an independent Tester records PASS and the code is committed, Delivery alone runs the new
   CLI with `--requirement-id R2.3-005` to append, in the state-machine-enforced order: prior
   `terminal_failure` classified
   `collaboration/routing` with incomplete modeling-quality result; one unique `+3`
   `budget_authorization` referencing this user decision; and `repair_authorization` bound to the
   exact next-run baseline and the independently passed routing-fix commit. Verify cap/start/active
   counts and unchanged R2.3-002 hash before any reservation.

## Failure behavior

- Unknown requirement ID, alternate formal root, wrong increment, invalid/duplicate ID/reference,
  early or wrong-order/run authorization, forged record, config drift or concurrent authorization
  fails before append or leaves exactly one valid append.
- A larger cap or valid but incomplete failure/budget prefix without the exact repair authorization
  still rejects reservation; the prefix resumes only through its exact next event. The sole repair
  without an immediately preceding budget is the fully qualified presemantic rebind above; all other
  repair attempts fail without byte changes.
- Presemantic release preserves the remaining count; `semantic_start` is the only consumption event.
- No direct JSONL edit, ledger rewrite, deletion, cap reset or cross-ledger migration is permitted.

## Excluded

- generic arbitrary-sized budgets, database-backed authorization, UI, remote coordination;
- changing R2.3-002 history or retry policy;
- automatic use of all three starts, concurrent Producers or extra successful slices;
- any real run before reviewed implementation, independent PASS and append-only authorization proof.
