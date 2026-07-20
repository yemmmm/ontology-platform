# R1.2-005 规则活动定义按需读取共享测试计划

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-005
- Design: `docs/delivery/designs/2026-07-20-r1-2-005-rule-definition-read-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-20-r1-2-005-rule-definition-explanation-delivery-record.md`
- Plan status: reviewed PASS; product implementation delivered and independently tested PASS on Round 1

## 1. Purpose and completion boundary

This is the single shared test plan for the future minimal R1.2-005 implementation. It tests the
existing REST Rule Definition read and the proposed thin MCP adapter, plus discovery, authorization,
replacement, language neutrality, response-size, and documentation boundaries.

The current delivery is documentation only. Documentation checks and plan review do not prove the
MCP tool exists. R1.2-005 stays `未实现` until a future implementation passes all product gates in
section 8 and an independent tester appends a PASS round in section 10.

## 2. Test levels and evidence

- Service/API tests prove the existing definition read and access check remain authoritative.
- MCP tests prove tool registration, input schema, authorization, successful-payload parity, and no
  Definition data on failure; transport-specific error mappings are not compared for equality.
- Integration tests against PostgreSQL prove replacement IDs, fresh Rules current-pointer selection,
  unchanged stored status, and persisted body value equality; mocks alone cannot prove replacement.
- Real runtime checks prove the registered MCP tool reads an authorized current definition after a
  service restart.
- Static contract tests prove ordinary Rules and Context responses do not gain definition bodies or
  explanation fields.

Volatile timestamps and transport-only envelopes may be excluded from parity comparison. Definition
identity, Ontology, Rule IRI, language, version, status, body, roles, output kind, and priority must
agree.

## 3. Fixtures

1. An authorized Ontology with the Dify reference Platform DSL rule
   `Resource-intensive synthetic workflow runs`, including a current definition whose body contains
   the `total_tokens` `gte` filter with integer `50000` and a direct
   `ResourceIntensiveWorkflowRun` result template.
2. A second authorized non-Platform-DSL rule: at least one `sparql_construct` definition; a
   `workflow_state_machine` definition is preferred when already available.
3. Two versions of one Rule so the Rules read model points to the replacement while the prior
   Definition retains whatever status the exercised existing write path stores.
4. An unauthorized foreign-Project Ontology with a known Definition ID.
5. A deleted/unknown Definition ID.

Fixtures use run-specific IDs and record exact ownership before mutation. Cleanup removes only those
identified resources; if ownership cannot be proved, cleanup is skipped and reported.

## 4. Functional cases

### 4.1 Compact discovery

| ID | Scenario | Expected result |
| --- | --- | --- |
| DS-01 | REST Rules read model for the authorized Ontology | current Rule identity, version, name, and `current_definition_id`; no `body` |
| DS-02 | MCP `get_ontology_read_model` with `model_name=rules` | same compact identity/current-definition semantics; no `body` |
| DS-03 | Context Query recalls a Rule | compact Rule metadata only; no raw body, normalized conditions, matched values, bindings, or explanation |
| DS-04 | caller asks for a wider existing field set | R1.2-005 does not silently inflate Rules or Context payloads |

### 4.2 Definition read and parity

| ID | Scenario | Expected result |
| --- | --- | --- |
| RD-01 | REST reads the current Platform DSL Definition ID | existing `SemanticRuleDefinitionRead` with exact persisted body and metadata |
| RD-02 | MCP reads the same ID | core result equals REST; no second interpretation schema |
| RD-03 | inspect the Dify body | `total_tokens`, `gte`, integer `50000`, and `ResourceIntensiveWorkflowRun` template are present |
| RD-04 | inspect the same body for `status=succeeded` | it is not invented as a rule condition |
| RD-05 | read a SPARQL CONSTRUCT definition | complete stored template returned without condition-tree conversion |
| RD-06 | read a workflow state machine when fixture exists | states/transitions returned unchanged; no threshold placeholders |
| RD-07 | JSON object insertion/key order differs | semantic JSON equality passes; arrays and scalar types remain exact |
| RD-08 | metadata contains stable IRI/literal/template values | values are neither summarized nor rewritten |

### 4.3 Replacement and history boundary

| ID | Scenario | Expected result |
| --- | --- | --- |
| VH-01 | read Rules summary after replacement | `current_definition_id` points to replacement and version matches it |
| VH-02 | read known prior Definition ID | authorized stored body may remain readable; currentness is false because it differs from a fresh Rules `current_definition_id`, regardless of stored status |
| VH-03 | read replacement Definition ID | status is `active`; body/version match current Rules summary |
| VH-04 | request history list/version selector | no new R1.2-005 capability is advertised or accepted |
| VH-05 | delete a Definition then read its ID | existing transport-specific unresolved-resource error; no Definition data or reconstruction from audit/history |

## 5. Authorization, failure, and privacy cases

| ID | Scenario | Expected result |
| --- | --- | --- |
| AU-01 | authorized Project read key reads own Definition | REST/MCP success |
| AU-02 | foreign-Project Definition ID | existing transport-specific authorization/not-found error; no Definition response or body |
| AU-03 | unknown random Definition ID | existing transport-specific unresolved/not-found error; no Definition response or body |
| AU-04 | missing/invalid credentials or missing read scope | existing authentication/authorization failure; no body |
| AU-05 | ordinary caller reads legacy unscoped Definition | remains hidden; administrator behavior is not broadened |
| AU-06 | MCP caller supplies actor/Project-like extra input | schema rejects or ignores it; server-derived identity controls access |
| AU-07 | body/metadata logging inspection | no new log path emits rule body, credentials, or foreign identifiers |
| AU-08 | storage contains prohibited secret material | test must not publish it as evidence; handle under existing secret/data-governance policy rather than inventing redaction semantics |

## 6. Consumer-boundary acceptance

The future real-runtime round uses only public supported capabilities:

1. discover the Dify Rule and its current Definition ID through the compact Rules read model;
2. read the stored body through REST and MCP;
3. separately read `total_tokens=128000`, the direct derived statement, and available lineage using
   existing query surfaces;
4. verify an external test Agent can infer `128000 >= 50000` and observe that `status=succeeded` is
   not a condition without any platform-generated trigger explanation;
5. run the existing Rule engine boundary fixture showing `49999` does not produce the target result
   and `50000` does, without duplicating that evaluation inside the read tool;
6. prove stale/unexecuted/lineage state continues to come from existing Run, derived-state, and
   lineage contracts rather than the definition-read response.

This section validates composability, not a natural-language wording produced by the platform. The
Agent's prose is not persisted as a new semantic fact.

## 7. Regression and documentation cases

| ID | Scenario | Expected result |
| --- | --- | --- |
| RG-01 | existing Rule create/update/delete tests | unchanged behavior and schemas |
| RG-02 | existing rule execution tests | unchanged evaluation and persistence |
| RG-03 | existing Rules/Context snapshots | no body or explanation payload growth |
| RG-04 | MCP registry/capability inventory | exactly one new read tool with one required Definition ID input |
| RG-05 | API reference | existing REST route remains unchanged and documented |
| RG-06 | MCP reference | future tool and response purpose documented after implementation |
| RG-07 | requirement/design/test/status consistency | R1.2-005 becomes `已实现` only after independent product PASS |
| RG-08 | production-code vocabulary scan | no Dify names or Platform-DSL-only response branch added |

## 8. Future implementation completion gate

Before R1.2-005 may be marked implemented:

1. focused REST/service/MCP tests for sections 4 through 7 pass;
2. full backend suite passes with `cd backend && uv run pytest`;
3. MCP registry and generated reference include the new tool;
4. real PostgreSQL replacement and cross-Project authorization tests pass;
5. the Dify and non-Platform-DSL fixtures prove raw-body and language-neutral behavior;
6. ordinary Rules/Context responses are measured or snapshot-tested to prove no payload expansion;
7. API/MCP/guide/requirement/design documentation is synchronized;
8. the local service is restarted and repository-required health endpoints pass;
9. GitNexus impact analysis precedes symbol edits and `detect_changes()` confirms expected scope;
10. an independent `requirement_tester` appends PASS and uniquely owned fixtures are cleaned.

Expected future commands include:

```bash
cd backend && uv run pytest
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

Frontend build and Playwright are required only if the future implementation changes frontend code
or a visible UI/capability surface.

## 9. Current documentation-only verification

This delivery runs only:

- requirement/design/test-plan path and terminology consistency checks;
- Markdown and `git diff --check` hygiene;
- independent plan review for evidence-backed Critical/High issues;
- GitNexus `detect_changes` before the documentation commit.

No backend test, MCP registry test, runtime restart, health check, or product acceptance result is
claimed in this phase.

## 10. Independent test rounds

No product test round has run because implementation is explicitly deferred. Future independent
testers append rounds here without deleting prior results.

| Round | Stable state | Result | Defects or unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| Pending | no implementation handoff | NOT RUN | all product cases deferred by approved scope | this plan |
| 2026-07-21T00:30+08:00 Round 1 | git:e988d11 (docs commit) plus uncommitted worktree implementation in `backend/app/mcp/tools/semantic.py` (`get_semantic_rule_definition`), `backend/app/mcp/runtime.py` (`MCP_TOOL_POLICIES` read/PROJECT_RESOURCE/mutates_state=False), `backend/tests/test_mcp_surface.py` (ALLOWED_TOOLS), new `backend/tests/test_semantic_rule_definition_mcp.py` (7 focused cases), and `docs/reference/mcp.md` (sync-interface-docs row). Tool signature has exactly one `rule_definition_id` input; no actor/project_id/created_by accepted. Adapter reuses `_ensure_rule_access` and `_rule_definition_read` from `app.api.semantic` (no new response model). No migration, configuration flag, or UI change. | PASS | Restricted: project test infrastructure uses SQLite in-memory + JSONB shim (no real PostgreSQL/Oxigraph). Sufficient for this contract because all rule-definition reads and Context Query `_rule_candidates` go through SQLAlchemy ORM, and `current_definition_id` re-pointing is service-layer logic independent of PostgreSQL-specific features. Real PostgreSQL replacement/cross-Project authorization parity deferred to runtime round. AU-07 log inspection best-effort: no rule body observed in stdout during test runs; project has no explicit body-audit log path. AU-08 secret material: no prohibited secret material present in fixtures. VH-02 stored-status of old definition not asserted (per design 4.3, only ID/body equivalence and fresh-pointer authority). DS-03/RG-03 covered by source inspection of `SemanticContextQueryService._rule_candidates` (candidate `data` keys limited to `definition_id`/`version`/`language`/`input_roles`/`output_kind`, no `body`) plus developer test file comment. RD-06 workflow_state_machine fixture not exercised; RD-05 SPARQL CONSTRUCT covered by developer test. | `cd backend && uv run pytest -q`: 792 passed, 6 skipped, 0 failed (80.48s). Focused suite `test_semantic_rule_definition_mcp.py` + `test_mcp_surface.py`: 10 passed. `cd backend && uv run ruff check app/ tests/`: 47 pre-existing errors (unchanged from clean-tree baseline `git stash`); R1.2-005-touched files (`app/mcp/tools/semantic.py`, `app/mcp/runtime.py`, `tests/test_semantic_rule_definition_mcp.py`, `tests/test_mcp_surface.py`) ruff clean. Independent tester scenarios executed ad-hoc (not committed): VH-02/VH-03 replacement (old ID body unchanged + new ID active + fresh `SemanticRuleModel.current_definition_id` points to v2), AU-04 unauthenticated call returns `ok=False` no data (note: scope model has no principal lacking implied `read`, since `model`/`admin` both imply `read`; the missing-read-scope case is structurally equivalent to unauthenticated), AU-06 inputSchema properties exactly `{rule_definition_id}` with no `actor`/`project_id`/`created_by`. |
