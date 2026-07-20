# R1.2-004 相关查询表达式联合语义上下文聚合设计

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-004
- Shared test plan:
  `docs/delivery/test-plans/2026-07-20-r1-2-004-related-query-aggregation-test-plan.md`
- Delivery record:
  `docs/delivery/records/2026-07-20-r1-2-004-related-query-aggregation-delivery-record.md`
- Contract frozen: 2026-07-20
- Plan review: PASS after two rounds; implementation remains pending
- Delivery scope: reviewed design only

## 1. Decision summary

R1.2-004 extends the existing Context Query REST route and MCP tool with a canonical
`queries: list[string]` input. One list contains related retrieval expressions for one topic. The
platform applies the same generic retrieval contract to each expression, fuses matching semantic
resources into one `primary_matches` list, and expands graph context for every returned match.

This is not a workflow query API. Workflow, Input, Node, Output, `hasNode`, and `node_order` remain
ordinary concepts and predicates in the Dify reference Ontology. The platform returns RDF
resources, predicates, values, topology, evidence, lineage, and completeness state; the consuming
Agent performs domain interpretation.

The public contract keeps `query: string` as a compatibility alias for a one-item list. New clients
and documentation use `queries`. No new route, MCP tool, fixed read model, or business-specific
response field is introduced.

## 2. Goals and non-goals

### 2.1 Goals

- Allow one topic to be expressed through several related words, phrases, or natural-language
  questions without assigning different platform semantics to those forms.
- Reuse R1.2-003 scope-safe lexical/vector retrieval and evidence tiers for every expression.
- Return one deterministic, deduplicated list with item-level evidence showing which expressions
  supported each match.
- Expand generic RDF context for all returned matches while retaining every source-match
  association and graph distance.
- Give matches and related context independent limits, truncation state, and continuation cursors.
- Preserve current single-query REST and MCP callers.
- Preserve failure-closed authentication, authorization, scope, parameter, and version behavior.

### 2.2 Non-goals

- Determine whether submitted expressions actually describe one topic. That grouping is the
  caller's responsibility.
- Distinguish a question from a phrase or keyword, infer a primary expression, or weight array
  position.
- Return per-expression result groups, `query_summary`, or separate expression status objects.
- Assert that two resources are equivalent merely because several expressions match them.
- Interpret predicates as workflow inputs, nodes, outputs, order, state, or another business model.
- Add a projection-template framework, reranker, new vector store, or query-history persistence.
- Implement product code, run implementation tests, or mark the requirement implemented in this
  documentation-only delivery.

## 3. Current state and constraints

The existing `SemanticContextQueryService.query` accepts one `query: str`, resolves a scope, gathers
RDF and semantic-retrieval candidates, fuses and sorts them, chooses `primary_matches`, and then
uses the unused portion of one global `limit` for related context. Neighborhood traversal starts
from a union of primary IRIs and does not preserve which primary match introduced a shared related
item. The response has one top-level `truncated` flag and no continuation cursor.

The REST Pydantic schema, MCP tool schema, and shared service method all currently require the
single string. Backward compatibility therefore applies at all three surfaces, not only at the
REST adapter.

The embedding client already accepts a list of texts. A live read-only probe showed that naively
executing three complete Context Queries took 5.426 seconds at depth 0 and 8.659 seconds at depth 1.
It also showed 22 to 31 related items for representative matches, while a full 20-match page could
consume the existing budget and return no context. The design consequently requires batched
retrieval, fusion before decoration/expansion, and independent budgets.

## 4. Public functional contract

### 4.1 Request

The canonical REST and MCP input uses `queries`:

```json
{
  "project_id": "project-id",
  "scope_mode": "ontologies",
  "ontology_ids": ["ontology-id"],
  "queries": ["客服工单", "客服", "工单详情"],
  "resource_types": ["concept", "instance"],
  "search_mode": "hybrid",
  "depth": 1,
  "limit": 20,
  "context_limit": 100
}
```

Compatibility input remains valid:

```json
{
  "project_id": "project-id",
  "scope_mode": "project",
  "query": "客服工单",
  "depth": 1,
  "limit": 20
}
```

The service normalizes the second request to `queries=["客服工单"]`. Requests must provide exactly
one of `queries` or `query`.

### 4.2 Validation and normalization

| Field | Contract |
| --- | --- |
| `queries` | 1 to 8 strings; canonical input |
| `query` | one string; compatibility alias only |
| each expression | trimmed length 1 to 2000 characters |
| aggregate expressions | at most 8000 characters after trimming |
| `depth` | integer 0 to 3; default 1 |
| `limit` | integer 1 to 100; default 20; match budget only |
| `context_limit` | integer 0 to 1000; default 100; related-context budget only |
| `match_cursor` | optional opaque continuation input; mutually exclusive with `context_cursor` |
| `context_cursor` | optional opaque continuation input; mutually exclusive with `match_cursor` |

Normalization reuses R1.2-003 text normalization. Normalized duplicate expressions execute once
and cannot increase expression-support count. The original list, including original order and
duplicates, remains available in the query echo for audit and replay. Item evidence refers to
original expression indexes so callers can correlate without caller-defined keys.

The platform does not reject or warn about expressions that appear unrelated. Valid expressions
always follow the same deterministic retrieval/fusion contract.

### 4.3 Response shape

The existing response remains the envelope. The query echo and pagination information are extended
without creating per-expression result groups:

```json
{
  "query": {
    "queries": ["客服工单", "客服", "工单详情"],
    "normalized_queries": ["客服工单", "客服", "工单详情"]
  },
  "result_status": "matched",
  "scope": {},
  "primary_matches": [
    {
      "id": "resource-id",
      "ontology_id": "ontology-id",
      "match": {},
      "matched_queries": [
        {"indexes": [0], "evidence_tier": "exact", "evidence": []},
        {"indexes": [1, 2], "evidence_tier": "semantic", "evidence": []}
      ],
      "fusion": {
        "best_evidence_tier": "exact",
        "support_count": 3
      }
    }
  ],
  "related_context": [
    {
      "id": "related-id",
      "root_paths": [
        {"root_match_id": "resource-id", "graph_distance": 1}
      ]
    }
  ],
  "matches_page": {
    "returned": 1,
    "truncated": false,
    "next_match_cursor": null
  },
  "context_page": {
    "returned": 1,
    "truncated": false,
    "next_context_cursor": null
  },
  "recall": {"completeness": "complete"},
  "truncated": false,
  "warnings": []
}
```

The field names inside existing match evidence remain governed by R1.2-003; the example above
specifies the new correlation and fusion meaning, not a replacement evidence schema.

For a legacy `query` request, the response retains existing `query.text` and
`query.normalized_terms` fields and may additionally expose the one-item list fields. A canonical
multi-expression response uses `queries` and `normalized_queries`; it does not assign a misleading
single `text` value. This keeps existing consumers stable while giving new consumers an unambiguous
shape.

`primary_matches` is the only match list. Its non-emptiness determines
`result_status=matched|no_match`. `related_context` is not counted when determining match status.
The compatibility top-level `truncated` remains the logical OR of `matches_page.truncated` and
`context_page.truncated`; new clients use the section-specific state.

### 4.4 Match identity, fusion, and ordering

Match identity remains `(ontology_id, resource_id)`. Identical IRIs in different Ontologies are not
merged. Evidence from all normalized expressions is accumulated on that identity.

Each expression independently applies the R1.2-003 candidate and evidence rules. Fusion does not
invent a new semantic score. The stable ordering keys are:

1. best R1.2-003 evidence tier, with exact label, altLabel, Mapping, or stable-ID evidence ahead of
   semantic-only evidence;
2. best score under the versioned R1.2-003 rule within that tier;
3. count of distinct normalized expressions supporting the resource;
4. the existing R1.2-003 stable tie-breaker: Ontology order, resource type, normalized label, and
   stable ID.

Input order is not an ordering key. Reordering the same expression multiset cannot change matches,
scores, support count, or final order. Duplicate expressions also cannot boost support.

Ambiguous resources remain separate matches. The platform never interprets multi-expression
support as equivalence or silently chooses one resource.

### 4.5 Generic context expansion

After fusion and match-page selection, the platform expands every returned match to the requested
depth:

- depth 0: matches only;
- depth 1: direct literal facts, incoming/outgoing relations, and adjacent resources;
- depth 2 or 3: explicit further graph traversal using the existing semantic boundary rules.

Expansion uses actual graph edges. It does not interpret distance as workflow step order or another
business hierarchy. Every related item records `root_paths`, an ordered list of
`{root_match_id, graph_distance}` objects containing the shortest distance from every returned
match that can reach it. A shared item is emitted once, with no lost root association. An
implementation may expose a scalar minimum distance as derived convenience, but it cannot replace
the per-root distances.

`context_limit=0` is a valid explicit request for matches without related context even when depth is
positive. It does not alter match recall. `depth=0` always produces an empty related-context page
and no context cursor.

### 4.6 Independent pagination

`limit` and `context_limit` are independent. Matching resources can never consume the context
budget, and context cannot reduce the number of returned matches.

- `next_match_cursor` continues the globally sorted match stream. The next response contains the
  next match page and starts context pagination for that new page.
- `next_context_cursor` continues only the context belonging to the current match page. It does not
  advance the match stream.
- A client may finish context before requesting the next match page, or intentionally skip the
  remaining context and continue matches. The server does not maintain mutable session state.

On continuation, the caller resubmits the original query/scope/filter/depth/page parameters and
exactly one corresponding input cursor (`match_cursor` or `context_cursor`). Both cursor inputs in
one request are invalid because one response cannot advance two independent streams atomically.

Cursors are versioned and integrity protected. They contain no raw query text. They bind a request
fingerprint covering the authenticated principal context, Project/Ontology scope, ordered original
queries, normalized execution set, filters, search mode, depth, relevant page size, cursor kind,
and the actual Ontology `workspace_version` and source signature used by the page. Cursor payloads
carry only the minimum continuation sort/root keys.

Authorization and scope resolution run again on every continuation request. Stable failures are:

- malformed, tampered, expired, or wrong-kind cursor: `400 invalid_context_cursor`;
- cursor used with different query/filter/depth/page parameters: `400 context_cursor_mismatch`;
- previously bound Ontology version/signature is no longer current: `409 context_snapshot_changed`,
  requiring a fresh query;
- authentication, authorization, or scope errors: existing R-008 failure-closed response.

A cursor signing-key rotation or process restart when only an ephemeral development key is
available invalidates outstanding cursors and returns `invalid_context_cursor`; it never resumes
against an unverified version. R1.2-007 capability discovery publishes cursor support, limits, and
the configured lifetime policy.

#### Context identity and total order

Before applying `context_limit`, all context producers (shape constraints, Operation targets,
literal statements, relations, and adjacent resources) use one canonical identity and total order.

- Context identity is `(ontology_id, kind, id)`, where `id` is the existing stable resource,
  statement, or derived shape-constraint identifier. Identity does not depend on producer or
  encounter order.
- All producers first union and sort the complete `root_paths` set for an identity. Root paths sort
  by the returned match's global match rank, then distance and stable match ID.
- The context stream sorts by minimum root distance, the existing resource-kind order, Ontology
  scope order, normalized label, and stable `id`. These keys form a total order; null labels use an
  empty normalized value.
- Pagination applies only after identity deduplication, root-path aggregation, and total sorting.
  A context cursor resumes strictly after the last context sort key within the exact bound root
  match page and semantic version.

SPARQL row order, producer phase, and which root encounters a shared item first cannot affect the
page contents. The implementation may use ordered merge queries instead of materializing the full
stream, but it must prove equivalence to this identity/order contract and must collect all root
paths for an emitted identity before returning it.

### 4.7 Completeness and failures

Authentication, authorization, scope, validation, and cursor/version failures reject the whole
request. They cannot be converted to partial results.

For retrieval availability, each distinct normalized expression follows R1.2-003 degradation. If
any expression lacks a required vector path, has a stale projection, or times out, available
lexical/vector evidence from all expressions is still fused and the overall recall completeness is
`degraded`. Warnings identify affected Ontologies and expression indexes without exposing
unauthorized resources.

A degraded response may still be `matched`. A degraded empty match list has
`result_status=no_match` for envelope compatibility, but `recall.completeness=degraded` explicitly
means it is not complete proof that the scoped Ontologies contain no relevant knowledge.

## 5. Service design

The future implementation uses one shared service path for REST and MCP. Both adapters must obtain
the current server-derived `AuthPrincipal` and convert it to a non-client-controlled principal
binding containing subject type, subject ID, authorized Project, and an effective-scope digest.
The REST route adds the same principal dependency already used by authorized semantic discovery.
The MCP runtime must forward the refreshed principal returned by `_authorize_tool` into the
Context Query callback/service instead of discarding it. A client-supplied actor or principal field
is never accepted for cursor binding.

The shared query pipeline then:

1. Receive the server-derived principal binding, validate exactly one public input form, and
   normalize it to an internal expression list.
2. Resolve and authorize the semantic scope once against that principal, capturing actual
   Ontology versions/signatures.
3. Normalize/deduplicate execution expressions while retaining original-index associations.
4. Gather lexical/RDF candidates for each expression with expression tags.
5. Submit all distinct expressions to the embedding provider in one bounded batch, then execute
   R1.2-003 exact vector scans within the already resolved scope.
6. Apply R1.2-003 evidence evaluation per expression, then deduplicate and fuse by semantic-resource
   identity.
7. Sort once, apply the match cursor and `limit`, and decorate selected matches once.
8. Expand the selected roots together, aggregate per-identity `root_paths`, apply the canonical
   context order, and then apply the independent context cursor and `context_limit`.
9. Aggregate per-expression/per-Ontology recall state and emit one response.

The implementation must not loop over the complete current Context Query pipeline because that
would repeat scope resolution, lineage work, and neighborhood expansion and would make pagination
composition unreliable. Expression count 8 and aggregate length 8000 are public safety limits;
internal RDF/vector candidate caps and an overall request deadline provide additional bounded work.
Provider batches may be split only if the configured provider advertises a lower batch limit, while
preserving the same result semantics.

## 6. Security, privacy, and consistency

- A server-derived principal binding is mandatory at the shared service/cursor codec; the same
  Project being visible to two principals does not make their cursors interchangeable.
- Scope and authorization precede candidate visibility, counts, similarities, warnings, and cursor
  creation.
- Queries, embeddings, and result text are not persisted as query history by this requirement.
- Logs use request IDs, counts, timing, status, and hashed request fingerprints rather than raw
  expressions.
- Cursor contents exclude raw query text and are integrity protected; every continuation rechecks
  current authorization and semantic versions.
- Fusion occurs only inside the resolved authorized scope. No cross-Ontology identity collapse or
  score leakage is allowed.
- RDF and retrieval projections keep their R1.2-003 authority and degradation rules; fusion does
  not create semantic facts or write back aliases/mappings.

## 7. Compatibility and rollout implications

The implementation is additive at public adapters but changes the shared service signature. REST,
MCP, service tests, API/MCP documentation, and capability discovery must be updated together.
Existing calls with `query`, existing defaults for `depth` and `limit`, and legacy single-query
response fields remain valid.

No data migration or backfill is required. Cursor support requires a versioned signer and
capability metadata. Deployments should configure a stable signing secret if cursors must survive
process restart; development fallback may be process-local and must advertise that limitation.

The rollout must retain a lexical-only/degraded test path because an environment can legitimately
have no current vector retrieval documents. Complete vector behavior requires an isolated current
projection fixture and cannot be inferred from lexical-only success.

## 8. Acceptance mapping

| Requirement outcome | Design mechanism | Test-plan coverage |
| --- | --- | --- |
| one related expression list, one fused response | canonical `queries`; one `primary_matches` | FQ-01, RS-01 |
| legacy callers remain valid | `query` compatibility alias across REST/MCP/service | BC-01 to BC-04 |
| exact evidence beats several weak matches | tier-first fusion ordering | FU-01 to FU-04 |
| order and duplicate invariance | equal weights; normalized dedupe | FU-05, FU-06 |
| all matches receive generic context | post-fusion multi-root expansion | CX-01 to CX-07 |
| independent budgets and continuation | two page states and cursor kinds | PG-01 to PG-10 |
| partial vector failure degrades safely | aggregate worst completeness | DG-01 to DG-05 |
| no workflow-specific platform behavior | generic RDF contract and unrelated fixture | BD-01 to BD-04 |
| authorization/version failure closes | scope-first execution and bound cursors | SC-01 to SC-07 |
| bounded cost | eight-expression/8000-char caps and one batched pipeline | PF-01 to PF-04 |

## 9. Deferred implementation surfaces

When implementation is authorized, the reviewed change is expected to touch the existing Context
Query request/response schemas, REST adapter, MCP tool, semantic context-query service, capability
discovery, focused backend tests, API/MCP/platform documentation, and runtime verification. Exact
file/symbol edits require fresh GitNexus impact analysis at that time.

This design does not authorize product edits and does not satisfy the requirement-delivery
implementation or independent-PASS completion gate. R1.2-004 remains `未实现`.
