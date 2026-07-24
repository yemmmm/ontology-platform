# R2.1-001 M2 受控建模流程演练共享测试计划

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M2
- Design:
  `docs/delivery/designs/2026-07-24-r2-1-001-m2-controlled-modeling-rehearsal-design.md`
- Status: completed — Round 1 PASS
- Test rounds: append-only

## Completion gates

1. 常驻服务模式在演练前后均为 `legacy_only`；临时后端明确为 `rdf_primary`。
2. 新 Project/Ontology/Build Session/Evidence 可读且归属一致。
3. 至少一轮故意错误 dry-run 留下可定位 finding，修正后的正式批次通过。
4. TBox、Shapes、published、draft、explicit-gap 均由 Modeling Batch `apply_atomic` 应用。
5. invalid Invocation 只做 dry-run 并被拒绝。
6. 显式读取角色为 `shapes` 的 Graph Set member，并传给 validation；演练日志保留请求与 run ID。
   独立测试通过场景内只读 ORM 脚本断言持久化 run 的 `shape_graph_iris` 非空且精确匹配该
   member。validation conforms，且已知无效 Invocation 使用同一 Shape 图时被拒绝；reasoning
   succeeds/consistent 并返回预期 subclass entailment。
7. scoped SPARQL 返回 B、A、完整 C -> B -> A 上下文、draft/latest 分离和显式未知。
8. 所有 Batch、Attempt、finding、Evidence、validation/reasoning run ID 可追踪。
9. 仓库与运行记录中不存在 semantic edit、raw load、direct DB/RDF write、validation bypass 或
   Dify 专属平台实现。
10. 独立测试 PASS，临时后端停止，常驻 backend/frontend 健康。

## Planned cases

| ID | Case | Expected evidence |
| --- | --- | --- |
| M2-01 | Active and isolated mode probes | regular `legacy_only`; isolated `rdf_primary` |
| M2-02 | Source pack integrity | M1 manifest hashes and pinned commit pass |
| M2-03 | Fresh workspace and Evidence | IDs, ready workspace, official/synthetic Evidence |
| M2-04 | Intentional invalid Shape payload | blocking finding identifies Item/path |
| M2-05 | Corrected TBox/Shapes dry-run and apply | validated then applied, immutable attempts retained |
| M2-06 | Published Fixture dry-run/apply | applied with Evidence and rationale |
| M2-07 | Invalid Invocation dry-run | 使用已应用 `shapes` member，拒绝缺少 `invokesTool` |
| M2-08 | Draft Fixture dry-run/apply | draft exists but is not active Latest |
| M2-09 | Explicit Gap dry-run/apply | gap has completeness state and `unknownDetail` |
| M2-10 | Managed validation | 正式请求显式 Shape IRI；只读 ORM 证明 run 精确持久化；conforms |
| M2-11 | Managed reasoning | succeeded/consistent; published version inferred as version |
| M2-12 | Published caller query | exactly B and A |
| M2-13 | Exact context query | one C -> B -> A row with invocation/binding/use positions |
| M2-14 | Draft query | draft version differs from active Latest |
| M2-15 | Explicit-gap query | known gap and unknown detail returned |
| M2-16 | Traceability | every critical failure maps input -> Batch -> finding -> correction |
| M2-17 | No-bypass review | scripts/logs/diff contain no forbidden write path |
| M2-18 | Handoff checklist | contains only required inputs, calls, feedback handling and outputs |
| M2-19 | Regression checks | scenario tests, focused backend tests, Ruff, `git diff --check` |
| M2-20 | Runtime closure | isolated process stopped; regular service and endpoints healthy |

## Required commands

```bash
uv run --directory backend python \
  ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py
cd backend && uv run pytest tests/test_modeling_batches_service.py \
  tests/test_semantic_validation.py tests/test_semantic_reasoning.py \
  tests/test_semantic_context_query_api.py
cd backend && uv run ruff check \
  ../docs/evaluation-scenarios/dify-workflow-impact-m2
cd backend && uv run python \
  ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/verify_validation_run.py \
  --run-id <run-id> --expected-shape-graph-iri <shape-graph-iri>
git diff --check
```

Independent testing must additionally review the retained live Project, Batch attempts, Evidence, validation and
reasoning runs; execute the read-only validation-run verifier and confirm it performs no SQL writes; reproduce the
known-invalid Invocation rejection with that Shape; repeat the scoped queries; verify the regular service mode; and
append a new round below. The M3 handoff checklist must not require ORM/database access.

## Test rounds

No M2 test round has run yet.

## Round 1 — 2026-07-24T16:45:29+08:00 — PASS

- Code/worktree: `8b640fa`; pre-existing shared changes were retained: modified delivery record and
  untracked M2 design, this test plan, and scenario package. No `backend/` or `frontend/` product
  path was modified by this test round. The isolated backend at `http://127.0.0.1:8012` was left
  running for the delivery owner.
- Runtime closure evidence: `GET 8001/api/health` returned `{"status":"ok"}`; authenticated
  `8001/api/semantic/canonical-mode` returned `legacy_only`. `GET 8012/api/health` returned OK and
  its authenticated canonical-mode response was `rdf_primary`; `5173/` returned HTTP 200 and
  `ontology-platform.service` was active. The same probes passed again after all acceptance checks.

### Executed cases and evidence

| Cases | Result | Evidence |
| --- | --- | --- |
| M2-01 | PASS | Live regular mode remained `legacy_only`; isolated mode was `rdf_primary` before and after testing. |
| M2-02 | PASS | `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py` passed 13/13, including pinned source-pack hashes. |
| M2-03 | PASS | Retained success Project `94dcff15-dc45-40d3-b85f-b9318d96aef6` and failed Project `eca27355-177d-45ab-a8d0-bb27573ab242` were both readable on 8012, each with its retained Ontology and three Evidence References. Success Build Session `f17db96f-c78f-4fbd-9089-b66899458469` was readable and matched the runtime record. |
| M2-04, M2-16 | PASS | Failed run `0d952d8711d7` retained `bad_shape` Batch `921c817d-55d0-4d83-a043-56b973d7bdfe` / Attempt `537cc41b-d60b-46b1-b90c-7ca994281473`, `dry_run`, `validation_failed`, blocking `shacl_violation`; it stopped at `draft-fixture`. Success run `2fde5cd4f165` explicitly corrects it and retains its own bad-shape finding. |
| M2-05, M2-06, M2-08, M2-09 | PASS | Success runtime record retains immutable `validated` then `applied` attempts for TBox/Shapes, published fixture, draft fixture, and explicit-gap fixture. Batch IDs: `09ee1f33-d292-47f2-b0f9-d1f4fdfc785c`, `b58bbc70-f4dc-4bbb-9a88-6ed4b6051613`, `8c1b4a11-3051-4966-a019-2f2dcf2b24c4`, and `b2819203-c760-4447-ba1c-fbe128ae4657`. |
| M2-07 | PASS | Original invalid Invocation Batch `038e056f-b7ec-4669-859a-3a3597bbbe4f` / Attempt `0807ce0b-9fa1-47b1-aeb9-591bacb5f9f6` is `dry_run`/`validation_failed` with `shacl_violation`. Independent repeat against the retained, same applied Shapes produced Batch `b12bf02c-32a6-4dd5-927a-0e5da84499e6` / Attempt `c510c80a-04dc-417c-808c-4901eed6180e`, also `dry_run`/`validation_failed`, one finding, no apply history and no workspace after-version. |
| M2-10 | PASS | `cd backend && uv run python ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/verify_validation_run.py --run-id 9225a4fc-d693-45b0-b5f8-473c1721c2a0 --expected-shape-graph-iri http://ontology-platform.local/semantic/graph/shapes/a093b881-f2ad-4fc9-aaa5-541e77a01992` returned `succeeded`, `conforms=true`, exact singleton `shape_graph_iris`, and `read_only=true`. Live Graph Set role `shapes`, runtime request, and persisted value all matched the same IRI. |
| M2-11 | PASS | Retained reasoning run `37bc96ef-de33-4856-962c-46d27b84b32d` was live-readable as `succeeded` and `consistent=true`; runtime record retains the expected RDFS subclass entailment. |
| M2-12–M2-15 | PASS | Re-executed the runner's scoped query contract on the retained success Project/Ontology. Row counts were callers=2 (exact B/A), context=1 (full C -> B -> A), draft=1 (not active Latest), gap=1 (explicit `unknownDetail`). |
| M2-17 | PASS | `test_scenario_m2.py` passed 5/5, including no-bypass and secret-persistence assertions. Static scan of executable runner found no semantic-edit, dataset-load, `validate=false`, SQLAlchemy/DB, or direct execute path. Retained runtime public-call lists use only public project/build-session/modeling-batch/Graph Set/validation/reasoning/SPARQL endpoints. Runtime JSON and rehearsal log contained no credentials, lease token, cookie, or Authorization value. |
| M2-18 | PASS | Reviewed `minimal-checklist.md`: it contains only environment probes, formal calls, feedback handling, required outputs and safe record preservation; it does not require ORM/database access or answer payloads. |
| M2-19 | PASS | `test_scenario_m2.py` 5/5; focused backend pytest command passed 69/69; `cd backend && uv run ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m2` passed; `git diff --check` passed. Pytest emitted five non-failing dependency deprecation warnings. |
| M2-20 | PASS | Isolated process was not stopped by the tester per scope; regular service is active and regular backend/frontend health checks are healthy. Delivery owner must stop 8012 after final acceptance, as planned. |

### Commands

```bash
uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py
uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/test_scenario_m2.py
cd backend && uv run pytest tests/test_modeling_batches_service.py tests/test_semantic_validation.py tests/test_semantic_reasoning.py tests/test_semantic_context_query_api.py
cd backend && uv run ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m2
cd backend && uv run python ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/verify_validation_run.py --run-id 9225a4fc-d693-45b0-b5f8-473c1721c2a0 --expected-shape-graph-iri http://ontology-platform.local/semantic/graph/shapes/a093b881-f2ad-4fc9-aaa5-541e77a01992
git diff --check
```

Additional authenticated read-only API checks verified both retained Projects, Evidence, Build Session,
Graph Set, validation/reasoning runs, Batch/Attempt histories, and re-ran scoped queries. The one
additional negative Modeling Batch request was deliberately `dry_run` only and is recorded above.

### Defects and conclusion

No product defect found. The earlier failed run is an expected, retained corrective-history record,
not a current regression: its `draft-fixture` failure is linked by `corrects_run_tag` to the complete
successful run. All completion gates are met. No development fix or retest is recommended.
