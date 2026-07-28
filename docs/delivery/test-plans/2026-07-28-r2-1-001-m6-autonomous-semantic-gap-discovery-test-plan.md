# R2.1-001 M6 建模 Agent 自主业务语义缺口发现共享测试计划

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M6
- Design:
  `docs/delivery/designs/2026-07-28-r2-1-001-m6-autonomous-semantic-gap-discovery-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`
- Status: planned — plan review PASS; gated on M5 completion and reviewed implementation
- Test rounds: append-only

## Fixed boundary

M6 uses the same bounded `C -> B -> A` business slice but a new raw multi-document source pack. The Agent
does not receive an ambiguity list, problem count, problem categories, hidden answers, M4/M5 artifacts,
answer model, Batch payload or acceptance query result.

The tester owns a hidden material-gap contract. It is an evaluation mapping, not an Agent prompt. Each
required gap must first pass the source-discoverability gate below.

## Completion gates

1. Independent source review proves every required material gap follows from a visible inconsistency,
   unresolved dependency or required consumer outcome; no arbitrary invisible fact is tested.
2. Static and mount inspection proves no Agent-visible file states or implies the expected gap count,
   category names or question checklist.
3. A fresh Agent performs a source-completeness assessment and asks every material business question
   without receiving the M4 explicit ambiguity list.
4. Every accepted question binds visible source evidence to a concrete model/query impact. Wording and
   ordering are not fixed.
5. Explicit facts are not re-asked. Extra questions pass only when the tester confirms their visible
   evidence and materiality; generic questionnaires or exhaustive enumeration fail.
6. Answers and uncertainty flow through M4's receipt, decision, Batch, validation, reasoning, query and
   blind-consumer evidence chain.
7. A fresh read-only Consumer recovers the applied target/contract, continuity result and explicit
   missing-score gap from public platform facts.
8. M4 regressions pass; no Dify-specific backend branch, persistent interview product or module-expansion
   work is introduced.
9. Independent tester appends a PASS round, cleans only uniquely owned runtime resources and verifies the
   normal service.

## Planned cases

| ID | Case | Expected evidence |
| --- | --- | --- |
| M6-01 | Raw-source pack | Separate realistic documents; hashes and mounts contain no explicit ambiguity list, count, categories or hidden answer. |
| M6-02 | Gap discoverability | Tester maps each required gap to visible source tension or an underdetermined required consumer outcome before Agent launch. |
| M6-03 | Autonomous completeness review | Agent records its own source-completeness assessment before principal schema modeling. |
| M6-04 | Invocation binding discovery | Agent notices that published versions exist while B's selected C version/binding rule is unresolved and asks a material business question. |
| M6-05 | Output identity discovery | Agent notices old/new contract fields lack an identity or evolution mapping and asks whether continuity is confirmed. |
| M6-06 | Missing-score discovery | Agent notices score absence is possible while downstream behavior is underdetermined and asks rather than inventing a fallback. |
| M6-07 | Question quality | Every required/extra question cites visible evidence and model/query impact; explicit facts, generic barrage and ontology-design delegation fail. |
| M6-08 | Serial clarification | One open question at a time; responses and receipts are bound without exposing hidden categories or answer count. |
| M6-09 | Answer-to-model chain | Confirmed decisions and uncertainty become immutable Batch rationale/model facts or named explicit gaps. |
| M6-10 | Formal semantic path | Shape dry-run/apply, invalid-instance rejection, candidate ABox or one eligible correction, validation, reasoning, governed query and completion pass. |
| M6-11 | Blind consumer | Fresh Consumer derives target contract, continuity/discontinuity and explicit unknown only from public semantic facts. |
| M6-12 | Isolation and regression | No M4/M5 answer artifact or Dify-specific platform code is exposed; focused M4 and applicable platform regressions pass. |
| M6-13 | Runtime closure | Owned isolated resources are removed; regular backend/frontend health checks pass. |

## Negative controls

- Replace the raw pack with a fixture containing the explicit M4 question list: isolation gate must fail
  before Agent launch.
- Add an expected count or category hint to a staged prompt: manifest/static gate must fail.
- Include an evaluator-required gap with no visible source tension or consumer consequence: the
  discoverability gate must reject the test itself.
- Submit one combined questionnaire or a generic “tell me everything uncertain” request: it cannot satisfy
  the three material cases.
- Ask the user to choose classes, properties, IRIs or Shapes: question-quality gate fails.
- Proceed using a default latest-version, successor mapping or missing-score fallback without a confirmed
  answer: final semantic audit fails.
- Produce a correct decision log without corresponding applied facts and consumer result: acceptance fails.

## Execution order

1. Freeze the raw source pack, hidden material-gap contract and hashes.
2. Run source-discoverability review independently of the modeling Agent.
3. Run static/mount/no-prior-artifact checks.
4. Start exactly one fresh autonomous discovery Producer.
5. If it completes, run independent semantic assertions and exactly one fresh blind Consumer.
6. Run focused M4 and relevant platform regressions, Ruff and `git diff --check`.
7. Clean uniquely owned isolated runtime resources and verify `ontology-platform.service`, `:8001` and
   `:5173`.

No live M6 Agent is authorized by this planning document alone. Execution remains gated on M5 completion,
reviewed implementation and a separate independent-test handoff.
