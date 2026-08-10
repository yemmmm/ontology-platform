# R2.3-005 Neutral Candidate Authoring Closure Plan

## Outcome

Use the last authorized start only after Modeling and Protocol share one small, scenario-neutral
ordinary-candidate authoring contract. Modeling must close the candidate's vocabulary, object ranges
and executable paths before the first delivery and every full revision. Protocol must pass the exact
entire delivered object to `build_candidate_receipt`; it must not synthesize a reduced conflict
candidate. This plan does not append start6 repair or consume start7.

## Start6 evidence

- Start6 `r23005-real-20260804t075359z-start6` proved the complete-revision repair: r2 was a full
  22,440-character replacement preserving all semantics, citations, constraints, dependencies and
  consumer queries, with no patch fields.
- r1 used the wrong ordinary item wrapper (`id,type,facts` rather than
  `item_id,item_kind,semantic`). r2 fixed it, then the full-current candidate exposed undeclared
  `upstreamOf`/`invokesAsPublishedTool`, an `affectedSubject: resource` range spanning unrelated
  classes without a declared common superclass, and further undeclared fact/Shape paths.
- Protocol rejected before any platform call. It also reconstructed reduced inputs for its mechanics
  calls instead of passing the exact delivered candidate. No dry-run, application or Acceptance
  result exists. Cleanup is complete and the canonical ledger is `7/6/0`; exactly one authorized
  slot remains.

## Current minimal scope

1. Add a short ordinary-neutral authoring checklist to Modeling instructions and the R2.3-005 task:
   - exact envelope `candidate_kind,candidate_revision,scope,constraints,items`, with `constraints`
     a list of non-empty strings;
   - every item uses a unique `item_id`, non-empty `item_kind`, object `semantic`, and optional
     `evidence_citations` as a list of objects;
   - every fact, relation and Shape predicate/path is declared exactly once in the current candidate;
   - every object-valued predicate has one declared target class; heterogeneous targets use a
     declared common superclass plus subclass bindings or separate predicates, never `resource` or
     an external placeholder;
   - all class/entity/predicate references close over the current candidate;
   - transport delivery/reply identities and Batch/platform IDs stay outside this neutral semantic
     candidate.
2. Add one tiny scenario-neutral immutable reference
   `modeling_team/references/platform-neutral-candidate-authoring.json` illustrating the envelope,
   declared predicate, common superclass/subclasses and Shape path. Stage it through the R2.3-005
   task to Modeling and Protocol only, and make both prompts reference it. It must not contain the
   C/B/A business corpus, competency answers, Batch/object-class IDs or a ready-made live model.
3. Clarify Protocol instructions: ordinary neutral required fields do not include Team Transport
   delivery/reply metadata; before every response, pass the exact entire current delivered object to
   `build_candidate_receipt`; never author a reduced/synthetic candidate merely to produce a conflict.
4. Add focused offline C99-C104 fixtures:
   - retained start6 r1 rejects the public wrapper;
   - retained r2 is a complete replacement but fails exact-current receipt because constraints are
     objects, then fails vocabulary/range/path closure after the mechanical envelope is corrected;
   - a corrected production-shaped candidate uses string constraints/unique item IDs, declares all
     used predicates, a common
     `UnknownAffectedSubject` superclass and subclasses, and executable paths, then reaches the
     ordinary neutral receipt;
   - static Modeling/Protocol/task projection sees the scenario-neutral checklist/example;
   - proof-bound R2.3-002, non-proof R2.3-005, complete-revision and Acceptance/lifecycle regressions
     remain unchanged.
5. Run focused, all R2.3-005 and complete `modeling_team` tests, Ruff, compile,
   `git diff --check`, GitNexus `detect_changes(compare main)`, and before/after live-ledger/start6
   immutability checks. No Agent Runtime, smoke, platform call, resource or ledger mutation.

## Sequencing and last-slot gate

1. Main records start6, this plan and C99-C104/I22-I23.
2. Plan Reviewer must confirm prompt/task/test-only scope and that the example is scenario-neutral.
3. Requirement Developer edits only the scenario-neutral reference, Modeling/Protocol instructions,
   R2.3-005 task and focused tests.
4. Independent Requirement Tester appends a new round to the existing shared test plan.
5. Only after clean commit and independent PASS may Delivery append one repair authorization for
   start6 bound to a fresh start7 baseline, then one reservation and one semantic start. No budget
   event; no concurrent run.

Start7 is the final authorized slot. Stop at the first full PASS. If it ends without full PASS,
cleanup and append its terminal event, then return to the user; do not increase cap or start again.

## Excluded

- exposing retained C/B/A candidate content, expected answers or hidden acceptance data to Agents;
- automatic semantic closure, candidate-history/patch merge or a new validator/state machine;
- mechanics/MCP/Runner/Runtime/platform/Acceptance/lifecycle/API/schema/UI changes;
- exact Batch authoring by Modeling, another Runtime smoke, new business slice, or platform writes;
- start7 before reviewed commit/independent PASS, and any start beyond cap 7.
