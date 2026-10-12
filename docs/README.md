# Documentation Map

This directory separates the current product contract from architecture decisions and historical
delivery evidence. Use the following locations for new documentation.

| Location | Purpose |
| --- | --- |
| [`requirements/`](requirements/) | Versioned product requirements. Select the version that owns the task; older versions apply through its declared baseline links. |
| [`reference/`](reference/) | Current public interface and terminology references: HTTP API, MCP tools, and glossary. |
| [`guides/`](guides/) | Operator and UI usage guides. |
| [`architecture/`](architecture/) | Current architecture overview, ADRs, and semantic-platform architecture history. |
| [`delivery/designs/`](delivery/designs/) | Requirement or initiative designs that freeze an intended solution. |
| [`delivery/implementation-plans/`](delivery/implementation-plans/) | Historical execution plans and implementation-status plans. |
| [`delivery/test-plans/`](delivery/test-plans/) | Shared and independent test plans, including their recorded rounds. |
| [`delivery/records/`](delivery/records/) | Append-only requirement delivery records. |
| [`delivery/modeling-retrospectives/`](delivery/modeling-retrospectives/) | Modeling-workflow retrospectives. |

## Current requirement entry points

- [v4.3 modeling efficiency, semantic retrieval, and rapid iteration](requirements/requirements-v4.3.md):
  target of at most two hours from a fresh start to complete independent semantic acceptance,
  with a later one-hour goal. Covers continuous approved execution, deterministic artifact handling,
  early public feedback, selective Delivery wakeups, and reference-based Judge evidence access.
  R4.3-001—007 have engineering acceptance evidence; complete semantic acceptance and the
  two-hour target remain unverified. Newly registered R4.3-008—012 cover structured semantic
  retrieval, nested neighbor previews, evidence-driven Consumer stopping, scoring evaluation
  before deciding on Jev, and reduced repeated computation. Their design and validation are pending;
  modeling remains paused.
  R4.3-013 registers optional file and directory references across existing authorized Agent
  interactions, with the handoff format chosen by each Agent; refinement and design are complete,
  independent design review/testing passed, and engineering implementation plus independent
  functional Round 3 passed. See its [delivery record](delivery/records/2026-10-11-r4-3-013-delivery-record.md);
  real Agent behavior improvements and independent semantic quality remain unverified.
  R4.3-014 requires recovery to reconcile actual completed content before continuing remaining work;
  existing recovery paths and partial prompt fixes should be reused, with real-run effects unverified.
  R4.3-015 registers staged modeling/feedback and trust in explicit successful apply receipts, removing
  routine duplicate write verification. Refinement must be discussed and confirmed with the user before
  implementation; Agents must not independently refine, finalize the design, or directly implement it.
- [v4.2 five-tab frontend rewrite](requirements/requirements-v4.2.md): current frontend target;
  overview, graph-based model browsing, recall testing, roles and Grants, and settings. Requirements
  implemented; design review, developer verification and independent functional Round 1 PASS. Supersedes
  the v4.1 frontend scope.
- [v4.1 frontend workbench adaptation](requirements/requirements-v4.1.md): previous frontend scope
  and its delivery evidence, retained for history.
- [v4.0 semantic modeling requirements](requirements/requirements-v4.0.md): the business-semantic,
  collaboration, authorization, and acceptance baseline inherited by the frontend versions.

## Placement rules

- Put new requirement designs, test plans, and delivery records in the matching `delivery/` subdirectory;
  use the existing date-prefixed filename convention.
- Update the source requirement when delivery status or acceptance evidence changes. Do not treat a design,
  plan, or delivery record as a replacement for the requirement.
- Keep current API/MCP inventories in `reference/`. They are generated and verified by
  `scripts/sync-interface-docs.py`; do not create a second manual interface inventory.
- Add hard-to-reverse architectural decisions as ADRs under `architecture/decisions/`.
- Retain historical documents rather than moving them back into current reference/guidance locations.
