# Documentation Map

This directory separates the current product contract from architecture decisions and historical
delivery evidence. Use the following locations for new documentation.

| Location | Purpose |
| --- | --- |
| [`requirements/`](requirements/) | Versioned product requirements. `requirements-v1.0.md` remains the authoritative global target-state reference. |
| [`reference/`](reference/) | Current public interface and terminology references: HTTP API, MCP tools, and glossary. |
| [`guides/`](guides/) | Operator and UI usage guides. |
| [`architecture/`](architecture/) | Current architecture overview, ADRs, and semantic-platform architecture history. |
| [`delivery/designs/`](delivery/designs/) | Requirement or initiative designs that freeze an intended solution. |
| [`delivery/implementation-plans/`](delivery/implementation-plans/) | Historical execution plans and implementation-status plans. |
| [`delivery/test-plans/`](delivery/test-plans/) | Shared and independent test plans, including their recorded rounds. |
| [`delivery/records/`](delivery/records/) | Append-only requirement delivery records. |
| [`delivery/modeling-retrospectives/`](delivery/modeling-retrospectives/) | Modeling-workflow retrospectives. |

## Placement rules

- Put new requirement designs, test plans, and delivery records in the matching `delivery/` subdirectory;
  use the existing date-prefixed filename convention.
- Update the source requirement when delivery status or acceptance evidence changes. Do not treat a design,
  plan, or delivery record as a replacement for the requirement.
- Keep current API/MCP inventories in `reference/`. They are generated and verified by
  `scripts/sync-interface-docs.py`; do not create a second manual interface inventory.
- Add hard-to-reverse architectural decisions as ADRs under `architecture/decisions/`.
- Retain historical documents rather than moving them back into current reference/guidance locations.
