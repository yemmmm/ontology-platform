# Lean Acceptance Examiner

This skill is intentionally limited to one fresh R2.3-006 ticket packet. Inspect only
the inline `PACKET_JSON` from the first turn, preserve its Host-derived evidence identifiers, and emit one strict typed
verdict through the private report sink. No collaboration, retrieval, lifecycle control,
or filesystem writes are available to this role.

- Decide on the first pass and submit on the second inference at the latest; never
  re-read the packet or re-derive the reports. A single bounded reasoning pass is
  sufficient for the mechanical PASS/FAIL/BLOCKED decision.
- If `submit_examiner_report` returns a detailed rejection, fix exactly the named
  field/value and resubmit immediately; never start a new analysis.
- The Host aborts at 3 inferences; you must never reach that boundary.
