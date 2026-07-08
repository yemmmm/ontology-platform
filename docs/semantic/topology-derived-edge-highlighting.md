# Topology Derived Edge Highlighting

## Context

The Stage 2 graph-derived `EntitiesPage` renders entity topology from the `entity-list` and
`entity-relations` read models. Those read-model rows already carry `assertion_kind` and
`source_graph_iri`, so the frontend can distinguish:

- `asserted` facts from source ontology/data graphs.
- `owl_inferred` facts from the effective reasoning-result graph.
- `rule_derived` facts from the effective rule-result graph.

The topology view should keep business context visible while making reasoning and rule output
visibly inspectable. Users need to see which edges are derived without losing the asserted graph
around them.

## Decision

Use visual focus rather than hard filtering for derived edge inspection.

The existing graph layer control keeps its data-scope meaning:

- Fact graph: read `asserted`.
- Reasoning graph: read `asserted-plus-reasoning`.
- Rule graph: read `asserted-plus-rules`.
- Complete view: read `full-working-view`.

Within those scopes, the canvas styles edges by assertion kind:

- Asserted edges use the neutral topology style.
- OWL-inferred edges use the reasoning accent.
- Rule-derived edges use the rule accent.
- Stale derived edges stay visible but use dashed styling.

Reasoning graph and Rule graph automatically enter a matching derived focus:

- Reasoning graph highlights `owl_inferred` / `inferred` edges and fades non-reasoning edges.
- Rule graph highlights `rule_derived` edges and fades non-rule edges.

Complete view exposes a focus selector:

- Context: show all assertion kinds with only kind colors.
- Reasoning: highlight reasoning edges and fade others.
- Rules: highlight rule-derived edges and fade others.

Node/edge selection and search remain higher-priority interaction states. When a user selects a
node or edge, the existing neighborhood highlight behavior takes over so the local inspection path
is not obscured by global derived focus.

## UX Rules

- Do not hide non-target edges in derived focus. Set low opacity so the user keeps topology context.
- Do not add list surfaces for derived facts. The topology remains the primary surface.
- Keep the detail panel selection-driven. It appears only after selecting a node or edge.
- Use labels users understand: Fact, Reasoning, Rule.
- Keep result-graph IRIs out of the default visible detail panel unless the user opens a deeper
  governance/debug surface.

## Implementation Notes

- `EntitiesPage` maps relation `assertion_kind` into `ForceGraphEdge.kind`.
- `EntitiesPage` maps stale relation metadata into `ForceGraphEdge.stale` when present.
- `ForceGraphCanvas` writes `kind` and `stale` to Cytoscape edge data.
- `ForceGraphCanvas` receives an optional `derivedFocus` prop with `reasoning`, `rules`, or `null`.
- Cytoscape selectors provide base kind styling; focus classes provide temporary dim/highlight.

## Acceptance Checks

- Fact graph still requests `include=asserted`.
- Reasoning graph requests `include=asserted-plus-reasoning` and automatically highlights reasoning
  edges when present.
- Rule graph requests `include=asserted-plus-rules` and automatically highlights rule-derived edges
  when present.
- Complete view requests `include=full-working-view` and exposes the Context/Reasoning/Rules focus
  selector.
- Existing node/edge selection still opens the detail panel and clears the full-width graph layout.
