# R1.2-005 规则活动定义按需读取设计

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-005
- Shared test plan:
  `docs/delivery/test-plans/2026-07-20-r1-2-005-rule-definition-read-test-plan.md`
- Delivery record:
  `docs/delivery/records/2026-07-20-r1-2-005-rule-definition-explanation-delivery-record.md`
- Contract frozen: 2026-07-20
- Plan review: PASS after three rounds; implementation remains pending
- Delivery scope: documentation and reviewed future implementation contract only

## 1. Decision summary

R1.2-005 adds no rule interpreter and no resource-trigger explanation API. It closes one narrower
consumer gap: after discovering a Rule and its `current_definition_id` through the compact Rules read
model, an authorized Agent can read that persisted Rule Definition through both REST and MCP.

The existing REST `GET /api/semantic/rule-definitions/{rule_definition_id}` and its
`SemanticRuleDefinitionRead` response remain authoritative. A future MCP tool named
`get_semantic_rule_definition` accepts the same definition ID and reuses the same service,
authorization, and serializer. It does not construct a second response model.

The stored `body` is the rule explanation available to the consuming Agent. The Agent combines it
with existing facts, Rule Runs, derived statements, currentness state, and lineage. The platform does
not paraphrase the body, extract a universal condition tree, repeat matched resource values, or infer
business meaning.

## 2. Goals and non-goals

### 2.1 Goals

- Expose the existing authorized Rule Definition by-ID read through MCP.
- Preserve REST/MCP parity by sharing the current read service and response serializer.
- Keep ordinary Rules and Context Query responses compact.
- Return each supported rule language exactly in its persisted JSON `body` representation.
- Treat the Rules summary's `current_definition_id` as the only current-version authority.
- Reuse existing Project/Ontology authorization without adding a new authorization model.

### 2.2 Non-goals

- Add a resource-specific trigger explanation, dry evaluation, or new Rule execution mode.
- Normalize Platform DSL, SPARQL, and workflow state machines into one condition model.
- Extract or duplicate conditions, operators, thresholds, matched values, bindings, result
  statements, lineage trees, or natural-language explanations in ordinary recall.
- Change rule creation, update, deletion, execution, current-definition selection, or storage.
- Add a Rule history list, version selector, release-version query, or new UI.
- Change effective classification, derived-pointer integrity, Rule Run, statement, or lineage
  contracts owned by R1.2-006 and v1.0 R-005/R-006.
- Implement product code, run product acceptance, restart services, or mark R1.2-005 implemented in
  this documentation-only delivery.

## 3. Current state and constraints

The fixed Ontology Rules read model, also exposed as MCP `get_ontology_read_model`, returns
`rule_id`, `rule_iri`, Rule status, `current_definition_id`, definition version, and name. It does not
return `body`, even when callers request a wider field set. Context Query similarly carries compact
Rule identity and definition metadata without embedding executable source.

The semantic REST API already provides list and by-ID reads. `_rule_definition_read` returns the
persisted `body` and existing definition metadata. `get_rule_definition` resolves the definition,
then `_ensure_rule_access` applies the authenticated principal's Project boundary. HTTP pre-auth
currently maps an unresolved ID differently from a resolved foreign-Project ID; this design does
not claim or introduce cross-transport error normalization.

MCP currently registers `submit_semantic_rule_definition` and `run_semantic_rule`, but no definition
read. The gap is therefore a transport capability, not a missing repository, schema, normalization,
or evaluation service.

Definitions support `platform_dsl`, `sparql_construct`, and `workflow_state_machine`. Their bodies
have different native structures. Only Platform DSL guarantees `when`/`then` clauses and supported
filter operators. Returning stored bodies avoids false cross-language equivalence.

## 4. Public functional contract

### 4.1 Discovery remains compact

The Agent first reads `model_name=rules` for an authorized Ontology. Each item continues to expose
the current Definition ID without a body:

```json
{
  "rule_id": "stable-rule-id",
  "rule_iri": "urn:example:resource-intensive",
  "status": "active",
  "current_definition_id": "definition-v5-id",
  "version": "sha256:...",
  "name": "Resource-intensive synthetic workflow runs"
}
```

R1.2-005 does not add `detail_available`, embedded source, explanation, or condition fields. The
presence of `current_definition_id` is already the continuation handle.

### 4.2 Definition read

The canonical reads are:

- REST: `GET /api/semantic/rule-definitions/{rule_definition_id}` (existing);
- MCP: `get_semantic_rule_definition(rule_definition_id)` (future thin adapter).

The identifier is a Rule Definition ID, not the stable semantic Rule ID or Rule IRI. The caller uses
the compact Rules read model when it wants the current definition. This preserves the existing
version model and avoids adding ambiguous selector precedence.

The MCP adapter invokes the same definition service, access check, and serializer as REST. Its core
result is the existing `SemanticRuleDefinitionRead` contract, including:

- `id`, `ontology_id`, `rule_iri`, `name`, `language`, `version`, and `status`;
- stored JSON `body` without semantic rewriting;
- `input_roles`, `output_kind`, `uses_inferred_facts`, `requires_review`, and `priority`;
- existing safety, creation, timestamp, and metadata fields already exposed by REST.

JSON object key order is not semantic and need not be preserved, but keys, arrays, scalar types,
IRIs, literals, operators, and templates must be value-equivalent to the persisted body. The MCP
adapter must not omit fields merely because a rule language does not use Platform DSL structure.

### 4.3 Current and historical behavior

The Rules read model's `current_definition_id` is the sole authority for which definition is
current. If a definition is replaced after discovery, reading the previously returned ID may still
return that stored definition. Its `status` may be `superseded` or may retain another existing value
because current write paths do not maintain old-definition status identically. A fresh Rules read
returns the replacement ID; R1.2-005 does not add an `is_current` field or repair version lifecycle.

R1.2-005 adds no history enumeration. An authorized caller that already knows an old Definition ID
may read it through the existing by-ID contract and receives its stored status unchanged. A deleted
or unknown ID follows the existing transport-specific unresolved-resource error mapping and returns
no Definition data. Release-version and historical discovery remain outside this scope.

### 4.4 Authorization and errors

- REST continues to derive the principal from authentication; MCP uses its registered read policy
  and server-derived principal rather than accepting Project or actor identity from tool input.
- A Definition attached to an Ontology is readable only when that Ontology belongs to the
  principal's authorized Project/scope.
- Unknown, deleted, and foreign-Project IDs disclose no Rule Definition body or response data.
  Existing REST and MCP pre-authorization error codes/messages remain transport-specific and are
  not normalized by R1.2-005.
- Existing unscoped legacy definitions remain restricted to the current administrator behavior;
  R1.2-005 does not broaden them to ordinary consumers.
- REST and MCP must agree on the core successful Definition payload. Failures retain the current
  transport-specific error code/message and are compared only for the absence of Definition data.

## 5. Consumer composition boundary

For the reference acceptance scenario, the Agent obtains three independent kinds of existing data:

1. the stored Platform DSL body from this definition read;
2. `total_tokens=128000` and other resource facts from Context Query, a fixed read model, or scoped
   SPARQL;
3. the direct `ResourceIntensiveWorkflowRun` statement and its Rule Run/lineage/currentness from
   existing derived and lineage capabilities.

The Agent can observe from the raw body that the filter is `gte(total_tokens, 50000)`, that the
result template asserts `ResourceIntensiveWorkflowRun`, and that `status` is not an input condition.
The platform does not return the sentence “the rule triggered because 128000 >= 50000”. It also does
not claim a trigger merely because a body can be evaluated hypothetically. Existing persisted Run,
statement, and lineage state remain the evidence that execution produced a result.

## 6. Compatibility and rollout

- No database migration, configuration flag, response expansion, frontend change, or new runtime
  dependency is required by the reviewed future implementation.
- Existing REST paths and response fields remain unchanged.
- Existing Rules/Context responses remain unchanged, so their payload size and consumer complexity
  do not increase.
- The future implementation adds the MCP tool to the registry and generated MCP reference, then
  verifies parity against real authorization and stored definitions.
- R1.2-005 remains `未实现` until that product change passes the shared plan and independent testing.

## 7. Acceptance mapping

| Requirement outcome | Design surface |
| --- | --- |
| discover current definition without body inflation | existing compact Rules read model |
| read current Platform DSL source | REST by-ID plus thin MCP parity tool |
| preserve all supported languages | unchanged stored `body` and `language` |
| recognize replacement | compare the requested ID with a fresh Rules `current_definition_id` |
| prevent unauthorized body access | existing REST/MCP ownership resolution and access checks |
| interpret reference threshold/result | consuming Agent composes body, facts, statement, and lineage |
| avoid platform-side business interpretation | explicit non-goals and no explanation fields |

## 8. Documentation-only completion boundary

This delivery is complete when the requirement, this design, the shared test plan, and delivery
record agree; an independent plan reviewer reports no evidence-backed Critical/High issue; Markdown
and diff checks pass; GitNexus confirms documentation-only scope; and the artifacts are committed.
No backend/frontend test or runtime health result is claimed because no product code changes.
