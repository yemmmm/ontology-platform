# Dify Workflow-as-Tool impact: M1

This is a small, offline-reproducible ontology scenario for R2.1-001 M1. It is
an evolving model/test checklist, not a Dify integration or a platform feature.

## Questions fixed by this slice

1. Given a published deletion of `C.quality_score:number`, which caller workflow
   versions are reachable through actual `ToolInvocation` joins?
2. Can a reader recover the C -> B -> A invocation, binding, and variable-use
   context without the ontology assigning a business impact or severity?
3. Can a Current Draft deletion be returned as a draft while being kept off the
   active Latest path, and can an incomplete structure be rejected?

The fixtures are deliberately synthetic: C is **Content Quality Scoring
Workflow**, B is **Content Generation Workflow**, and A is **Campaign
Publication Workflow**. They are not claims about a built-in Dify application.

## Model choices and boundaries

`Workflow` owns versions; `WorkflowVersion` is the publication unit and owns
its call sites. A `WorkflowTool` targets a version and a `ToolInvocation`
represents one stable call site in a caller version. `VariableBinding` links
the source and destination variables at that invocation; `VariableUse` records
a downstream consumer. `ChangeSet` records an explicit deletion.
`completeness` is mandatory for each returned path component; the isolated
explicit-gap fixture uses `unknownDetail` rather than silently omitting a
component.

Publication is a controlled literal (`latest`, `superseded`, or
`current-draft`) because this minimal slice needs a state distinction, not a
new workflow-state product model. The published query uses the SPARQL property
path `hasInvocation/invokesTool/toolTargetsVersion` for caller reachability.
The RDFS check is only a supported subproperty entailment
(`producesVariable -> referencesVariable`); it does **not** infer the C -> B
-> A chain. A separate standard-RDFS closure regression keeps `VariableUse`
distinct from `Variable`.

Files:

- `ontology.ttl` -- candidate TBox and controlled-state vocabulary.
- `shapes.ttl` -- executable minimum structure and completeness constraints.
- `fixtures/` -- isolated published, draft, explicit-gap, and invalid graphs.
- `queries/` -- read-only SPARQL checks, including property-path reachability.
- `source-pack/` -- immutable supplemental official-source manifest and page.
- `tests/test_scenario.py` -- the complete offline acceptance command.
- `iteration-log.md` -- append-only modelling decisions and next candidate.

## Provenance boundary

Official-source claims are limited to the Dify documentation in `source-pack/`:
a Workflow starting with User Input can be a Tool; Output, Version Control,
Start/User Input and IF/ELSE pages are cited as generic product semantics.
The C/B/A facts are marked `synthetic-fixture`. The tests return topology,
contracts and completeness only. Any statement that B or A is really affected,
or any severity, remains a consuming Agent/query inference.

## Offline acceptance

From repository root:

```bash
uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py
```

Expected result: 12 tests pass. They verify every source hash without network,
parse all RDF, validate positive/draft fixtures with SHACL, reject the invalid
fixture, invoke `backend/scripts/dev_owl_reasoner.py` for one supported RDFS
entailment, and evaluate the published/draft SPARQL assertions in fresh graphs.

## Managed-platform runtime acceptance

Use a fresh, owned Project/Ontology and its managed workspace. Do **not** use
`datasets:load` or any raw dataset loader.

1. Create an Evidence Reference for `source-pack/manifest.json`, quoting the
   pinned Tools page hash and its CC-BY-4.0 attribution.
2. Start a Build Session and read `get_modeling_context`. If the active product
   write mode enables the Modeling Batch canonical writer, dry-run the portions
   expressible by its structured commands before applying them.
3. Apply `ontology.ttl` plus one fixture with the governed generic
   `submit_semantic_edit` Turtle path to the workspace editable graph, with the
   Evidence Reference, audit reason, and `validate=true`. Apply Shapes by the
   same governed path to the workspace shape graph. This is the generic
   canonical writer path, not an ungoverned loader.
4. Run `run_semantic_validation`, the configured reasoning operation, and
   `semantic_sparql_query` scoped to that Project/Ontology with
   `queries/published-deletion.rq` or `queries/draft-only.rq`. Persist returned
   report/run IDs as Build Session evidence.

Independent Round 3 successfully applied this candidate's ontology, Shapes and
published Fixture through the governed generic edit path with `validate=true`;
managed validation conformed, configured reasoning was consistent, and scoped
SPARQL returned the complete C -> B -> A context. The uniquely named temporary
Project was then deleted and confirmed absent.

The active runtime reports `SEMANTIC_PRODUCT_WRITE_MODE=legacy_only`, so even a
simple Modeling Batch dry-run is blocked by the canonical-writer gate. Because
that gate prevents an active-runtime probe, this scenario does not claim that
the structured Modeling Batch surface can or cannot encode every statement in
the candidate. The verified governed semantic-edit path is sufficient for M1;
canonical Modeling Batch enablement and any remaining generic expressiveness
question stay explicit follow-ups and are not reasons to add Dify-specific
code or use a raw loader.
