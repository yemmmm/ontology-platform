# Semantic Stage 3 — Publish Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `PublicationPage` as a graph-set readiness dashboard, replace `VersionsPage` with `GraphSetHistoryPage`, and hard-cut remove all legacy version/proposal/publication backend code.

**Architecture:** Three new read-model templates (`publication-readiness`, `graph-set-history-list`, `graph-set-delta`) layered on the existing Phase 6 read-model framework. Publish = lock-all-graphs via existing editability endpoint + export package. Diff = RDF delta between two graph sets. Legacy `governance.py` router, two services, eleven schemas, twelve Postgres models, two MCP tool files, and ten test files are deleted in one release.

**Tech Stack:** Python 3.11 / FastAPI / Pydantic / SQLAlchemy / Alembic / Oxigraph / `rdflib`; React 18 / TypeScript / Vite / Playwright; pytest.

**Spec:** `docs/delivery/designs/2026-07-06-semantic-stage3-publish-design.md`

---

## Phase A — Backend Read-Models

**Subagent:** `stage3-backend-readmodels`
**Dependencies:** none (builds on existing Phase 6 framework)
**Verify gate:** `uv run pytest backend/tests/test_semantic_stage3_e2e.py backend/tests/test_semantic_read_model_stage3_execution.py -x` passes; `uv run pytest backend/tests/ -x` passes (legacy tests still green).

### Task A1: Add `publication-readiness` template and composer

**Files:**
- Modify: `backend/app/services/semantic_sparql_templates.py` (append to `_TEMPLATES` after `fact-audit-queue`)
- Modify: `backend/app/services/semantic_read_model.py` (add `_compose_publication_readiness` + helpers)
- Test: `backend/tests/test_semantic_read_model_stage3_execution.py` (new file)

- [ ] **Step A1.1: Add template registration**

Append to `_TEMPLATES` in `semantic_sparql_templates.py`:

```python
"publication-readiness": ReadModelTemplate(
    name="publication-readiness",
    projection_version="1",
    required_roles=["asserted_ontology", "asserted_data"],
    needs_reasoning=True,
    needs_rules=True,
    default_limit=1,
    assertion_kind=None,
    evidence_status=None,
    primary_iri_variable="",
    body="""# template: publication-readiness
# Single-row composer. Body is intentionally empty; the service
# delegates to ``_compose_publication_readiness`` which reuses the
# graph-set-staleness and missing-evidence aggregators.
""",
),
```

- [ ] **Step A1.2: Write failing execution test**

Create `backend/tests/test_semantic_read_model_stage3_execution.py`:

```python
"""Stage 3 read-model template execution tests.

Validates that the new templates route SPARQL to the correct named
graphs and produce the envelope shape defined in
docs/delivery/designs/2026-07-06-semantic-stage3-publish-design.md §4.
"""
import pytest
from backend.app.services.semantic_sparql_templates import _TEMPLATES


def test_publication_readiness_template_registered():
    t = _TEMPLATES["publication-readiness"]
    assert t.projection_version == "1"
    assert "asserted_ontology" in t.required_roles
    assert "asserted_data" in t.required_roles
    assert t.needs_reasoning is True
    assert t.needs_rules is True
    assert t.default_limit == 1
```

- [ ] **Step A1.3: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_semantic_read_model_stage3_execution.py::test_publication_readiness_template_registered -v`
Expected: PASS (template already added in A1.1).

- [ ] **Step A1.4: Add composer skeleton with stub**

In `semantic_read_model.py`, locate `_compose_fact_audit_queue` (around line 415). Below it, add:

```python
def _compose_publication_readiness(
    self,
    graph_set_id: str,
    field_set: str,
    allow_stale_derived: bool,
) -> SemanticReadModelEnvelope:
    """Compose the publication readiness row for a graph set.

    Aggregates staleness, missing-evidence, open edits, projection
    freshness, and editability state into a single envelope.
    See spec §4.1 for the field contract.
    """
    members = self._scope.members_for(graph_set_id)
    staleness = self._compose_graph_set_staleness(
        graph_set_id, field_set="detail", allow_stale_derived=allow_stale_derived
    )
    missing = self._missing_evidence_count(graph_set_id)
    open_edits = self._open_edits_count(graph_set_id)
    editable_graphs = [
        {"graph_iri": m.graph_iri, "role": m.role}
        for m in members
        if m.editable
    ]
    gates = self._evaluate_publication_gates(
        staleness=staleness,
        missing_evidence=missing,
        open_edits=open_edits,
        editable_graph_count=len(editable_graphs),
        projection_freshness=self._projection_freshness(graph_set_id),
    )
    row = {
        "graph_set_id": graph_set_id,
        "ready": all(g["status"] == "passed" for g in gates),
        "gates": gates,
        "blockers": [g["label"] for g in gates if g["status"] == "blocked"],
        "warnings": [g["label"] for g in gates if g["status"] == "warning"],
        "editable_graph_count": len(editable_graphs),
        "editable_graphs": editable_graphs,
        "last_published_at": self._last_published_at(graph_set_id),
    }
    return SemanticReadModelEnvelope(
        graph_set_id=graph_set_id,
        projection_name="publication-readiness",
        projection_version="1",
        field_set=field_set,
        allow_stale_derived=allow_stale_derived,
        rows=[row] if field_set == "detail" else [{
            "graph_set_id": graph_set_id,
            "ready": row["ready"],
            "blockers": row["blockers"],
            "warnings": row["warnings"],
        }],
        truncated=False,
    )
```

Add helpers below the composer:

```python
def _open_edits_count(self, graph_set_id: str) -> int:
    # Counts SemanticEditAuditModel rows with status='pending' for
    # any member graph_iri of this set. Stage 2 left these uncommitted
    # edits; Stage 3 surfaces them as a publication blocker.
    from backend.app.repositories.models import SemanticEditAuditModel
    iris = {m.graph_iri for m in self._scope.members_for(graph_set_id)}
    return (
        self._session.query(SemanticEditAuditModel)
        .filter(
            SemanticEditAuditModel.graph_iri.in_(iris),
            SemanticEditAuditModel.status == "pending",
        )
        .count()
    )

def _projection_freshness(self, graph_set_id: str) -> dict:
    # Returns {manifest_name: {fresh: bool, last_run_at: str|None}}.
    from backend.app.repositories.models import SemanticProjectionManifestModel
    rows = (
        self._session.query(SemanticProjectionManifestModel)
        .filter_by(graph_set_id=graph_set_id)
        .all()
    )
    out = {}
    for r in rows:
        out[r.name] = {
            "fresh": r.last_run_at is not None,
            "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
        }
    return out

def _last_published_at(self, graph_set_id: str) -> str | None:
    from backend.app.repositories.models import SemanticGraphSetModel
    row = (
        self._session.query(SemanticGraphSetModel)
        .filter_by(id=graph_set_id)
        .first()
    )
    if row and row.graph_set_metadata:
        v = row.graph_set_metadata.get("last_published_at")
        return str(v) if v else None
    return None

def _evaluate_publication_gates(
    self, *, staleness, missing_evidence, open_edits,
    editable_graph_count, projection_freshness,
) -> list[dict]:
    gates: list[dict] = []
    for member in staleness["rows"][0].get("members", []) if staleness["rows"] else []:
        pass  # staleness gates folded below
    staleness_row = staleness.rows[0] if staleness.rows else {}
    for kind in ("validation", "reasoning", "rule"):
        member_staleness = next(
            (m for m in staleness_row.get("members", [])
             if m.get("role", "").startswith(kind)
             or kind in m.get("role", "")),
            None,
        )
        state = (member_staleness or {}).get("staleness_state", "unknown")
        gates.append({
            "gate": f"{kind}_stale",
            "status": "passed" if state == "fresh" else (
                "warning" if state == "stale" else "blocked"
            ),
            "details": member_staleness or {},
            "label": f"{kind} is {state}",
        })
    gates.append({
        "gate": "missing_evidence",
        "status": "passed" if missing_evidence == 0 else "blocked",
        "details": {"count": missing_evidence},
        "label": f"{missing_evidence} facts missing evidence",
    })
    gates.append({
        "gate": "open_edits",
        "status": "passed" if open_edits == 0 else "warning",
        "details": {"count": open_edits},
        "label": f"{open_edits} pending semantic edits",
    })
    gates.append({
        "gate": "projection_freshness",
        "status": "passed" if all(
            p["fresh"] for p in projection_freshness.values()
        ) else "warning",
        "details": projection_freshness,
        "label": "projection manifest freshness",
    })
    return gates
```

Also register the composer in the dispatch table (find the section that maps template name → composer function, near `_compose_graph_set_staleness` registration):

```python
# Add to the composer dispatch map:
"publication-readiness": _compose_publication_readiness,
```

If the dispatch is via an `if name == ...:` chain, add a branch there instead.

- [ ] **Step A1.5: Add execution test for composer routing**

Append to `test_semantic_read_model_stage3_execution.py`:

```python
def test_publication_readiness_composer_routes_to_dispatch(
    monkeypatch, fake_graph_set_with_members
):
    """The read-model service must dispatch `publication-readiness` to
    the dedicated composer (not the generic SPARQL path)."""
    from backend.app.services import semantic_read_model as mod
    called = {}
    def stub(self, *args, **kwargs):
        called["yes"] = True
        return {"rows": [{"ready": True}]}
    monkeypatch.setattr(
        mod.SemanticReadModelService,
        "_compose_publication_readiness",
        stub,
        raising=True,
    )
    svc, graph_set_id = fake_graph_set_with_members
    svc.read_model(
        graph_set_id=graph_set_id,
        model_name="publication-readiness",
        field_set="detail",
    )
    assert called.get("yes") is True
```

Add the `fake_graph_set_with_members` fixture to a new `backend/tests/conftest_stage3.py` (imported into the test module). The fixture reuses the pattern from `backend/tests/test_semantic_stage2_e2e.py` lines 30–80 (FakeStore + in-memory SQLite + registered graph set). Copy that fixture wholesale and rename.

- [ ] **Step A1.6: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_semantic_read_model_stage3_execution.py -v`
Expected: PASS (both tests).

- [ ] **Step A1.7: Commit**

```bash
git add backend/app/services/semantic_sparql_templates.py \
        backend/app/services/semantic_read_model.py \
        backend/tests/test_semantic_read_model_stage3_execution.py \
        backend/tests/conftest_stage3.py
git commit -m "feat(semantic): publication-readiness read-model template and composer (Stage 3 §4.1)"
```

### Task A2: Add `graph-set-history-list` template

**Files:**
- Modify: `backend/app/services/semantic_sparql_templates.py`
- Modify: `backend/app/services/semantic_read_model.py`
- Test: `backend/tests/test_semantic_read_model_stage3_execution.py`

- [ ] **Step A2.1: Add template registration**

Append to `_TEMPLATES`:

```python
"graph-set-history-list": ReadModelTemplate(
    name="graph-set-history-list",
    projection_version="1",
    required_roles=[],   # composer-owned; reads from Postgres
    needs_reasoning=False,
    needs_rules=False,
    default_limit=50,
    assertion_kind=None,
    evidence_status=None,
    primary_iri_variable="",
    body="""# template: graph-set-history-list
# Single-row composer that returns the list of graph sets in scope.
# Reads from SemanticGraphSetModel joined with members and derived
# pointers; see spec §4.2.
""",
),
```

- [ ] **Step A2.2: Write failing execution test**

Append to `test_semantic_read_model_stage3_execution.py`:

```python
def test_graph_set_history_list_returns_sets_in_scope(
    fake_graph_set_with_members, second_graph_set_same_scope
):
    """Composer returns both graph sets in scope with status derived
    from member editability and derived pointer timestamps."""
    svc, _ = fake_graph_set_with_members
    other_id = second_graph_set_same_scope
    envelope = svc.read_model(
        graph_set_id=other_id,  # any set in scope works; composer queries by scope
        model_name="graph-set-history-list",
        field_set="summary",
    )
    assert envelope.projection_name == "graph-set-history-list"
    rows = envelope.rows
    assert rows["total"] >= 2
    ids = {r["graph_set_id"] for r in rows["graph_sets"]}
    assert other_id in ids
    for r in rows["graph_sets"]:
        assert r["status"] in ("editable", "locked", "superseded")
        assert "created_at" in r
        assert "locked_at" in r
        assert "member_count" in r
```

Add a `second_graph_set_same_scope` fixture to `conftest_stage3.py` that builds a second graph set under the same scope as the first.

- [ ] **Step A2.3: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_semantic_read_model_stage3_execution.py::test_graph_set_history_list_returns_sets_in_scope -v`
Expected: FAIL (composer not yet implemented; KeyError or empty rows).

- [ ] **Step A2.4: Implement composer**

Add to `semantic_read_model.py`:

```python
def _compose_graph_set_history_list(
    self,
    graph_set_id: str,
    field_set: str,
    allow_stale_derived: bool,
) -> SemanticReadModelEnvelope:
    """List graph sets in the same scope as ``graph_set_id``."""
    from backend.app.repositories.models import (
        SemanticGraphSetModel,
        SemanticGraphSetMemberModel,
        SemanticDerivedResultPointerModel,
    )
    from sqlalchemy import func

    anchor = (
        self._session.query(SemanticGraphSetModel)
        .filter_by(id=graph_set_id)
        .first()
    )
    if anchor is None:
        return SemanticReadModelEnvelope(
            graph_set_id=graph_set_id,
            projection_name="graph-set-history-list",
            projection_version="1",
            field_set=field_set,
            allow_stale_derived=allow_stale_derived,
            rows={"graph_sets": [], "total": 0},
            truncated=False,
        )
    sets = (
        self._session.query(SemanticGraphSetModel)
        .filter_by(scope_type=anchor.scope_type, scope_id=anchor.scope_id)
        .order_by(SemanticGraphSetModel.created_at.desc())
        .all()
    )
    out = []
    for s in sets:
        members = (
            self._session.query(SemanticGraphSetMemberModel)
            .filter_by(graph_set_id=s.id)
            .all()
        )
        any_editable = any(m.editable for m in members)
        latest_pointer = (
            self._session.query(func.max(SemanticDerivedResultPointerModel.became_current_at))
            .join(
                SemanticGraphSetMemberModel,
                SemanticGraphSetMemberModel.graph_iri == SemanticDerivedResultPointerModel.result_graph_iri,
            )
            .filter(SemanticGraphSetMemberModel.graph_set_id == s.id)
            .scalar()
        )
        out.append({
            "graph_set_id": s.id,
            "status": "editable" if any_editable else "locked",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "locked_at": (s.graph_set_metadata or {}).get("locked_at"),
            "source_signature": s.source_signature,
            "member_count": len(members),
            "latest_derived_pointer_at": (
                latest_pointer.isoformat() if latest_pointer else None
            ),
            "ready": None,
        })
    return SemanticReadModelEnvelope(
        graph_set_id=graph_set_id,
        projection_name="graph-set-history-list",
        projection_version="1",
        field_set=field_set,
        allow_stale_derived=allow_stale_derived,
        rows={"graph_sets": out, "total": len(out)},
        truncated=False,
    )
```

Register in the dispatch map alongside `publication-readiness`.

- [ ] **Step A2.5: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_semantic_read_model_stage3_execution.py -v`
Expected: PASS (all tests so far).

- [ ] **Step A2.6: Commit**

```bash
git add backend/app/services/semantic_sparql_templates.py \
        backend/app/services/semantic_read_model.py \
        backend/tests/test_semantic_read_model_stage3_execution.py \
        backend/tests/conftest_stage3.py
git commit -m "feat(semantic): graph-set-history-list read-model template (Stage 3 §4.2)"
```

### Task A3: Add `graph-set-delta` template

**Files:**
- Modify: `backend/app/services/semantic_sparql_templates.py`
- Modify: `backend/app/services/semantic_read_model.py`
- Test: `backend/tests/test_semantic_read_model_stage3_execution.py`

- [ ] **Step A3.1: Add template registration**

Append to `_TEMPLATES`:

```python
"graph-set-delta": ReadModelTemplate(
    name="graph-set-delta",
    projection_version="1",
    required_roles=[],   # composer queries two graph sets
    needs_reasoning=False,
    needs_rules=False,
    default_limit=200,
    assertion_kind=None,
    evidence_status=None,
    primary_iri_variable="",
    body="""# template: graph-set-delta
# Composer-driven. Reads the ``target`` query param to identify the
# second graph set, then for each role present in both sets computes
# the CONSTRUCT diff. See spec §4.3.
""",
),
```

- [ ] **Step A3.2: Wire `target` query param through the route**

In `backend/app/api/semantic.py` `read_model` (around line 1175), the route already accepts arbitrary extra query params via `**kwargs` or an explicit list. Check the signature. If `target` is not yet accepted, add it:

```python
@router.get("/graph-sets/{graph_set_id}/read-models/{model_name}")
def read_model(
    graph_set_id: str,
    model_name: str,
    include: str | None = None,
    allow_stale_derived: bool = False,
    field_set: str = "summary",
    limit: int | None = None,
    offset: int = 0,
    entity: str | None = None,
    class_iri: str | None = None,
    kind: str | None = None,
    target: str | None = None,  # NEW — used by graph-set-delta
):
    service = _read_model_service()
    envelope = service.read_model(
        graph_set_id=graph_set_id,
        model_name=model_name,
        field_set=field_set,
        allow_stale_derived=allow_stale_derived,
        limit=limit,
        offset=offset,
        filters={
            "include": include,
            "entity": entity,
            "class_iri": class_iri,
            "kind": kind,
            "target": target,  # NEW
        },
    )
    return envelope
```

Verify by reading the current `read_model` signature and adapting (don't duplicate logic; just thread `target` through the existing `filters` dict).

- [ ] **Step A3.3: Write failing execution test**

Append to `test_semantic_read_model_stage3_execution.py`:

```python
def test_graph_set_delta_returns_per_role_triple_diff(
    fake_graph_set_with_members, second_graph_set_with_one_fewer_entity
):
    """Given two graph sets differing by one entity, the delta composer
    reports one removed triple group in the asserted_data role."""
    svc, base_id = fake_graph_set_with_members
    target_id = second_graph_set_with_one_fewer_entity
    envelope = svc.read_model(
        graph_set_id=base_id,
        model_name="graph-set-delta",
        field_set="detail",
        filters={"target": target_id},
    )
    rows = envelope.rows
    assert rows["base_graph_set_id"] == base_id
    assert rows["target_graph_set_id"] == target_id
    role_map = {r["role"]: r for r in rows["roles"]}
    assert "asserted_data" in role_map
    ad = role_map["asserted_data"]
    assert ad["counts"]["removed"] >= 1
    assert len(ad["removed"]) >= 1
    # removed triples have subject/predicate/object keys
    assert {"subject", "predicate", "object"} <= set(ad["removed"][0])
```

Add a `second_graph_set_with_one_fewer_entity` fixture that builds a graph set whose `graph/data/{id}` contains one fewer entity than the base.

- [ ] **Step A3.4: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_semantic_read_model_stage3_execution.py::test_graph_set_delta_returns_per_role_triple_diff -v`
Expected: FAIL (composer not implemented).

- [ ] **Step A3.5: Implement composer**

Add to `semantic_read_model.py`:

```python
def _compose_graph_set_delta(
    self,
    graph_set_id: str,
    field_set: str,
    allow_stale_derived: bool,
    target: str | None = None,
    limit: int = 200,
) -> SemanticReadModelEnvelope:
    """Diff two graph sets by named graph role."""
    if not target:
        raise CanonicalSemanticWriteError(
            "graph-set-delta requires ?target=<other_graph_set_id>"
        )
    base_members = {m.role: m for m in self._scope.members_for(graph_set_id)}
    target_members = {m.role: m for m in self._scope.members_for(target)}
    roles = sorted(set(base_members) | set(target_members))
    out = []
    for role in roles:
        b = base_members.get(role)
        t = target_members.get(role)
        b_triples, b_count = self._role_triples(b, limit) if b else (set(), 0)
        t_triples, t_count = self._role_triples(t, limit) if t else (set(), 0)
        added = list(t_triples - b_triples)[:limit]
        removed = list(b_triples - t_triples)[:limit]
        out.append({
            "role": role,
            "base_graph_iri": b.graph_iri if b else None,
            "target_graph_iri": t.graph_iri if t else None,
            "added": [self._triple_dict(x) for x in added],
            "removed": [self._triple_dict(x) for x in removed],
            "counts": {
                "added": max(0, len(t_triples - b_triples)),
                "removed": max(0, len(b_triples - t_triples)),
            },
        })
    return SemanticReadModelEnvelope(
        graph_set_id=graph_set_id,
        projection_name="graph-set-delta",
        projection_version="1",
        field_set=field_set,
        allow_stale_derived=allow_stale_derived,
        rows={
            "base_graph_set_id": graph_set_id,
            "target_graph_set_id": target,
            "roles": out,
        },
        truncated=any(
            r["counts"]["added"] > limit or r["counts"]["removed"] > limit
            for r in out
        ),
    )

def _role_triples(self, member, limit: int) -> tuple[set, int]:
    """Run CONSTRUCT ?s ?p ?o WHERE { GRAPH <iri> { ?s ?p ?o } } and
    return (frozenset_of_triples, total_count)."""
    query = (
        f"CONSTRUCT WHERE {{ GRAPH <{member.graph_iri}> {{ ?s ?p ?o }} }}"
    )
    # Reuse the existing RDF store accessor; count via a sibling SELECT.
    graph = self._rdf_store.construct(query)
    triples = set()
    for s, p, o in graph:
        triples.add((str(s), str(p), str(o)))
        if len(triples) >= limit:
            break
    count_q = (
        f"SELECT (COUNT(*) AS ?c) WHERE {{ GRAPH <{member.graph_iri}> "
        f"{{ ?s ?p ?o }} }}"
    )
    count_result = self._rdf_store.select(count_q)
    total = int(count_result[0]["c"]["value"]) if count_result else 0
    return triples, total

def _triple_dict(self, triple: tuple) -> dict:
    s, p, o = triple
    return {"subject": s, "predicate": p, "object": o}
```

`CanonicalSemanticWriteError` is already imported at the top of the file. If the RDF store accessor signature differs, adapt — confirm by reading `backend/app/repositories/rdf_store.py` and matching the existing pattern in `_compose_fact_audit_queue`.

Register in dispatch map.

- [ ] **Step A3.6: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_semantic_read_model_stage3_execution.py -v`
Expected: PASS.

- [ ] **Step A3.7: Commit**

```bash
git add backend/app/api/semantic.py \
        backend/app/services/semantic_sparql_templates.py \
        backend/app/services/semantic_read_model.py \
        backend/tests/test_semantic_read_model_stage3_execution.py \
        backend/tests/conftest_stage3.py
git commit -m "feat(semantic): graph-set-delta read-model template (Stage 3 §4.3)"
```

### Task A4: Stage 3 backend happy-path e2e (steps 1–8 of spec §11)

**Files:**
- Create: `backend/tests/test_semantic_stage3_e2e.py`

- [ ] **Step A4.1: Write the e2e file with steps 1–8**

Each step is its own pytest function. The file reuses the `conftest_stage3.py` fixtures and the Stage 2 e2e harness pattern from `backend/tests/test_semantic_stage2_e2e.py`. Steps 1–8 cover the readiness happy path (steps 9–11 cover history/delta, added in Task A5).

```python
"""Stage 3 spec §11 happy-path coverage.

Steps 1–8 land here. Steps 9–11 (history list + delta) land in
a separate commit after the delta composer exists.
"""
import pytest
from backend.tests.conftest_stage3 import (
    fake_graph_set_with_members,
    PREFIX, GRAPH_PREFIX, ONTOLOGY_GRAPH, DATA_GRAPH,
)


def test_step1_build_graph_set(fake_graph_set_with_members):
    svc, graph_set_id = fake_graph_set_with_members
    assert graph_set_id.startswith("gs-")


def test_step2_seed_ontology(fake_graph_set_with_members, fake_store):
    """Run create_class canonical-write; verify the class lands in
    graph/ontology/{id}."""
    # Apply create_class via /canonical-writes:compile-and-apply
    # Inspect fake_store.captured_updates for the ontology graph IRI.
    # Assert the UPDATE targeted <{ONTOLOGY_GRAPH}>.
    ...


def test_step3_seed_data(fake_graph_set_with_members, fake_store):
    """create_entity canonical-write; verify it lands in graph/data/{id}."""
    ...


def test_step4_trigger_validation_and_reasoning(fake_graph_set_with_members):
    """POST /graph-sets/{id}/validation-runs and /reasoning-runs."""
    ...


def test_step5_readiness_blocking(fake_graph_set_with_members):
    """ready=false because open_edits gate is warning (just wrote)."""
    svc, gs = fake_graph_set_with_members
    env = svc.read_model(gs, "publication-readiness", field_set="detail")
    assert env.rows[0]["ready"] is False
    labels = [g["label"] for g in env.rows[0]["gates"]]
    assert any("pending semantic edits" in lbl for lbl in labels)


def test_step6_lock_ontology(fake_graph_set_with_members):
    """PATCH editability on ontology graph; readiness shows count--."""
    ...


def test_step7_lock_data_then_ready(fake_graph_set_with_members):
    """Lock data graph; readiness becomes ready=true."""
    ...


def test_step8_export(fake_graph_set_with_members):
    """GET /graph-sets/{id}/export; assert ontology + data graphs present."""
    ...
```

Fill in the `...` bodies by copying patterns from `test_semantic_stage2_e2e.py`. Each step calls real service methods (not HTTP) for speed.

- [ ] **Step A4.2: Run e2e**

Run: `uv run pytest backend/tests/test_semantic_stage3_e2e.py -v`
Expected: PASS (steps 1–8).

- [ ] **Step A4.3: Commit**

```bash
git add backend/tests/test_semantic_stage3_e2e.py
git commit -m "test(semantic): Stage 3 spec §11 steps 1–8 happy-path e2e"
```

### Task A5: History list + delta e2e (steps 9–11 of spec §11)

**Files:**
- Modify: `backend/tests/test_semantic_stage3_e2e.py`

- [ ] **Step A5.1: Append steps 9–11**

```python
def test_step9_build_second_graph_set(
    fake_graph_set_with_members, second_graph_set_with_one_fewer_entity
):
    """Sanity: the second fixture builds and is queryable."""
    svc, _ = fake_graph_set_with_members
    other = second_graph_set_with_one_fewer_entity
    env = svc.read_model(other, "graph-set-history-list", field_set="summary")
    assert env.rows["total"] >= 2


def test_step10_compute_delta(
    fake_graph_set_with_members, second_graph_set_with_one_fewer_entity
):
    svc, base = fake_graph_set_with_members
    target = second_graph_set_with_one_fewer_entity
    env = svc.read_model(
        base, "graph-set-delta",
        field_set="detail",
        filters={"target": target},
    )
    ad = next(r for r in env.rows["roles"] if r["role"] == "asserted_data")
    assert ad["counts"]["removed"] >= 1


def test_step11_history_list(fake_graph_set_with_members):
    svc, gs = fake_graph_set_with_members
    env = svc.read_model(gs, "graph-set-history-list", field_set="summary")
    assert any(r["graph_set_id"] == gs for r in env.rows["graph_sets"])
```

- [ ] **Step A5.2: Run**

Run: `uv run pytest backend/tests/test_semantic_stage3_e2e.py -v`
Expected: PASS (all 11 steps).

- [ ] **Step A5.3: Run full backend suite to confirm nothing regressed**

Run: `uv run pytest backend/tests/ -x`
Expected: PASS (Stage 2 e2e, Phase 6/7 API tests, read-model stage2 tests, etc.).

- [ ] **Step A5.4: Commit**

```bash
git add backend/tests/test_semantic_stage3_e2e.py
git commit -m "test(semantic): Stage 3 spec §11 steps 9–11 history list and delta"
```

---

## Phase B — Backend Hard-Cut Removals

**Subagent:** `stage3-backend-removal`
**Dependencies:** Phase A passing
**Verify gate:** `uv run pytest backend/tests/ -x` passes; the legacy `governance.py` router returns 404 for all its paths; the migration runs both forward and is rejected on downgrade.

### Task B1: Remove the `governance.py` router and its registration

**Files:**
- Delete: `backend/app/api/governance.py`
- Modify: `backend/app/api/routes.py:27` (remove `governance_router` import + include)
- Modify: `backend/app/main.py` or wherever the FastAPI app is assembled (search for any other registration)

- [ ] **Step B1.1: Confirm what imports `governance_router`**

Run: `grep -rn "governance_router\|from .governance\|from app.api.governance" backend/`
Expected: only `routes.py:27` and possibly `main.py`. Note every hit.

- [ ] **Step B1.2: Remove the include call**

In `routes.py`, delete the line that does `router.include_router(governance_router)` and the import at the top.

- [ ] **Step B1.3: Delete the router file**

```bash
git rm backend/app/api/governance.py
```

- [ ] **Step B1.4: Verify imports**

Run: `uv run python -c "from backend.app.api.routes import router; print(len(router.routes))"`
Expected: succeeds; route count drops by 13.

- [ ] **Step B1.5: Run test suite**

Run: `uv run pytest backend/tests/ -x -k "not stage3"`
Expected: many tests in `test_governance_service.py` and `test_publication_service.py` fail (expected; they are deleted in B7). Other tests pass.

### Task B2: Remove `services/publication.py` and `services/governance.py`

**Files:**
- Delete: `backend/app/services/publication.py`
- Delete: `backend/app/services/governance.py`
- Find and update any remaining importers

- [ ] **Step B2.1: Find importers**

Run: `grep -rn "from backend.app.services.publication\|from backend.app.services.governance\|services\.publication\|services\.governance" backend/`
Expected: only test files and the deleted router.

- [ ] **Step B2.2: Delete**

```bash
git rm backend/app/services/publication.py backend/app/services/governance.py
```

- [ ] **Step B2.3: Verify Python import graph still loads**

Run: `uv run python -c "import backend.app.services"`
Expected: succeeds.

### Task B3: Delete legacy schemas

**Files:**
- Modify: `backend/app/api/schemas.py`

- [ ] **Step B3.1: Delete these classes from `schemas.py`**

Remove:
- `OntologyVersionCreate` (around `:659`)
- `OntologyVersionRead` (`:663`)
- `VersionMutabilityUpdate` (`:679`)
- `ProposalCreate` (`:782`)
- `ProposalRead` (`:799`)
- `VersionDiffRead` (`:828`)
- `PublicationReadinessRead` (`:1099`)
- `PublicationConfirm` (`:1107`)
- `KnowledgeConflictRead` (search)
- `ConflictResolutionCreate` (search)

- [ ] **Step B3.2: Verify no remaining importers**

Run: `grep -rn "OntologyVersionRead\|ProposalRead\|VersionDiffRead\|PublicationReadinessRead\|PublicationConfirm\|KnowledgeConflictRead\|ConflictResolutionCreate\|VersionMutabilityUpdate\|OntologyVersionCreate\|ProposalCreate" backend/app/`
Expected: no hits.

- [ ] **Step B3.3: Verify Python imports**

Run: `uv run python -c "from backend.app.api import schemas"`
Expected: succeeds.

### Task B4: Delete legacy models

**Files:**
- Modify: `backend/app/repositories/models.py`

- [ ] **Step B4.1: Find every reference to legacy models in `app/`**

Run:
```bash
grep -rn "OntologyVersionModel\|ProposalModel\|ReviewBatchModel\|EvidenceModel\|ReviewDecisionModel\|ValidationRunModel\|PublicationGateModel\|FactClaimModel\|RuleDefinitionModel\|UnanchoredKnowledgeModel\|KnowledgeConflictModel\|VersionStatus" backend/app/
```
Expected: only hits inside `models.py` itself (since services are gone). Any external hit must be removed first.

- [ ] **Step B4.2: Remove the enum and the model classes from `models.py`**

Delete (in any order — they have no interdependencies after services are gone):
- `VersionStatus` enum
- `OntologyVersionModel`
- `ProposalModel`
- `ReviewBatchModel`
- `EvidenceModel`
- `ReviewDecisionModel`
- `ValidationRunModel` (legacy; `SemanticValidationRunModel` stays)
- `PublicationGateModel`
- `FactClaimModel` (legacy; semantic fact data lives in RDF)
- `RuleDefinitionModel` (legacy; `SemanticRuleDefinitionModel` stays)
- `UnanchoredKnowledgeModel`
- `KnowledgeConflictModel`

Also remove the `current_version_id` column from `OntologyModel` (around `:768`).

- [ ] **Step B4.3: Verify Python imports**

Run: `uv run python -c "from backend.app.repositories.models import OntologyModel; print('ok')"`
Expected: prints `ok`.

### Task B5: Migration `0017_drop_legacy_governance.py`

**Files:**
- Create: `backend/migrations/versions/0017_drop_legacy_governance.py`

- [ ] **Step B5.1: Write the migration**

```python
"""drop legacy governance tables (Stage 3 hard cut)

Revision ID: 0017_drop_legacy_governance
Revises: 0016_semantic_migration_tables
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_drop_legacy_governance"
down_revision = "0016_semantic_migration_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Children first; then parents. ontologies.current_version_id
    # FK to ontology_versions is dropped before its parent table.
    op.drop_constraint(
        "ontologies_current_version_id_fkey",
        "ontologies",
        type_="foreignkey",
    )
    op.drop_column("ontologies", "current_version_id")

    for table in (
        "review_decisions",
        "evidence",
        "review_batches",
        "validation_runs",
        "publication_gates",
        "fact_claims",
        "rule_definitions",
        "unanchored_knowledge",
        "knowledge_conflicts",
        "proposals",
        "ontology_versions",
    ):
        op.drop_table(table)


def downgrade() -> None:
    raise NotImplementedError(
        "Stage 3 hard-cut migration is one-way. Legacy data cannot be "
        "reconstructed once dropped. Restore from a pre-migration backup."
    )
```

If any constraint name differs in the deployed schema, adjust the `drop_constraint` call to match the actual name (check existing migration files for the convention used).

- [ ] **Step B5.2: Apply the migration against a fresh test DB**

Run: `uv run alembic upgrade head`
Expected: succeeds, no orphaned FK errors.

- [ ] **Step B5.3: Confirm downgrade refuses**

Run: `uv run alembic downgrade -1`
Expected: raises `NotImplementedError` (or Alembic wraps it).

- [ ] **Step B5.4: Commit**

```bash
git add backend/migrations/versions/0017_drop_legacy_governance.py
git commit -m "feat(db): migration 0017 drops legacy governance tables (Stage 3 §6.5)"
```

### Task B6: Remove legacy MCP tools

**Files:**
- Delete: `backend/app/mcp/tools/proposals.py`
- Delete: `backend/app/mcp/tools/publication.py`
- Modify: `backend/app/mcp/tools/__init__.py`

- [ ] **Step B6.1: Find registrations**

Run: `grep -n "register_proposals\|register_publication" backend/app/mcp/tools/__init__.py`
Expected: lines around `:17,18,28,32`.

- [ ] **Step B6.2: Remove the registrations**

Edit `__init__.py`: delete the two import lines and the two `register_*()` calls.

- [ ] **Step B6.3: Delete the files**

```bash
git rm backend/app/mcp/tools/proposals.py backend/app/mcp/tools/publication.py
```

- [ ] **Step B6.4: Update surface test**

In `backend/tests/test_mcp_surface.py`, remove `get_publication_readiness` (`:59`) and `publish_version` (`:92`) entries from the expected tool registry. The remaining tools should still match.

- [ ] **Step B6.5: Verify**

Run: `uv run pytest backend/tests/test_mcp_surface.py -v`
Expected: PASS.

### Task B7: Delete legacy tests

**Files:**
- Delete: `backend/tests/test_publication_service.py`
- Delete: `backend/tests/test_governance_service.py`
- Modify: `backend/tests/test_mcp_payloads.py` (remove proposal/publication payload cases)
- Modify: `backend/tests/test_v04_acceptance.py`, `test_v05_acceptance.py` (drop or rewrite lifecycle cases)

- [ ] **Step B7.1: Delete the two service test files**

```bash
git rm backend/tests/test_publication_service.py backend/tests/test_governance_service.py
```

- [ ] **Step B7.2: Audit `test_mcp_payloads.py`**

Run: `uv run pytest backend/tests/test_mcp_payloads.py -v`
Expected: failures for proposal/publication payload tests. Remove those test functions.

- [ ] **Step B7.3: Audit acceptance tests**

For each `test_v04_acceptance.py` and `test_v05_acceptance.py` function that walks `/versions/...` or `/proposals/...` endpoints:
- If the test verifies behavior that is now covered by `test_semantic_stage3_e2e.py`, delete it.
- If the test verifies orthogonal behavior (e.g., a UI flow that doesn't depend on the deleted endpoints), update it to skip or use the new endpoints.

Run: `uv run pytest backend/tests/test_v04_acceptance.py backend/tests/test_v05_acceptance.py -v`
Expected: PASS for remaining cases.

- [ ] **Step B7.4: Run full backend suite**

Run: `uv run pytest backend/tests/ -x`
Expected: PASS.

- [ ] **Step B7.5: Commit**

```bash
git add backend/tests/
git commit -m "chore(semantic): delete legacy publication/governance tests (Stage 3 §6.7)"
```

---

## Phase C — Frontend `PublicationPage`

**Subagent:** `stage3-frontend-publication`
**Dependencies:** Phase A + B passing
**Verify gate:** `cd frontend && npm run typecheck && npm run test` pass; manual smoke via `npm run dev` shows the readiness dashboard against a backend fixture.

### Task C1: Add `useGraphSetReadiness` hook

**Files:**
- Create: `frontend/src/hooks/useGraphSetReadiness.ts`

- [ ] **Step C1.1: Write the hook**

```typescript
import { useCallback, useEffect, useState } from "react";
import { readModel, WorkbenchRequest } from "../semanticApi";
import { useGraphSetId } from "./useGraphSetId";

export interface PublicationGate {
  gate: string;
  status: "passed" | "warning" | "blocked";
  details: Record<string, unknown>;
  label: string;
}

export interface PublicationReadinessRow {
  graph_set_id: string;
  ready: boolean;
  gates: PublicationGate[];
  blockers: string[];
  warnings: string[];
  editable_graph_count: number;
  editable_graphs: { graph_iri: string; role: string }[];
  last_published_at: string | null;
}

export interface PublicationReadinessEnvelope {
  graph_set_id: string;
  projection_name: "publication-readiness";
  projection_version: string;
  field_set: "summary" | "detail";
  rows: PublicationReadinessRow[];
}

export function useGraphSetReadiness(request: WorkbenchRequest) {
  const graphSetId = useGraphSetId();
  const [data, setData] = useState<PublicationReadinessRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!graphSetId) return;
    setLoading(true);
    setError(null);
    try {
      const env = await readModel<PublicationReadinessEnvelope>(
        request,
        graphSetId,
        "publication-readiness",
        { field_set: "detail" }
      );
      setData(env.rows[0] ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [request, graphSetId]);

  useEffect(() => {
    reload();
    const id = window.setInterval(reload, 30_000);
    return () => window.clearInterval(id);
  }, [reload]);

  return { data, loading, error, reload };
}
```

If `useGraphSetId` does not exist, search `frontend/src/hooks/` for the equivalent (Stage 2 pages use a context or prop). Match the existing convention.

- [ ] **Step C1.2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

### Task C2: Rewrite `PublicationPage.tsx`

**Files:**
- Modify: `frontend/src/pages/PublicationPage.tsx` (full rewrite, ~250 lines)
- Reference: `frontend/src/pages/ClassesPage.tsx` for the read-model + canonical-write pattern

- [ ] **Step C2.1: Write the new component**

```tsx
import { useState } from "react";
import { useGraphSetReadiness } from "../hooks/useGraphSetReadiness";
import { updateGraphEditability, buildGraphSetExportUrl, WorkbenchRequest } from "../semanticApi";
import { useTranslation } from "react-i18next";

interface Props {
  request: WorkbenchRequest;
  ontologyId: string;
  readOnly: boolean;
}

export function PublicationPage({ request, readOnly }: Props) {
  const { t } = useTranslation();
  const { data, loading, error, reload } = useGraphSetReadiness(request);
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);

  if (loading && !data) return <div>{t("common.loading")}</div>;
  if (error) return <div role="alert">{t("publication.readiness.error")}: {error}</div>;
  if (!data) return <div>{t("publication.readiness.empty")}</div>;

  const handlePublish = async () => {
    setPublishing(true);
    setPublishError(null);
    const locked: string[] = [];
    try {
      for (const g of data.editable_graphs) {
        await updateGraphEditability(request, g.graph_iri, { editable: false });
        locked.push(g.graph_iri);
      }
      window.location.href = buildGraphSetExportUrl(request, data.graph_set_id);
    } catch (e) {
      setPublishError(
        t("publication.readiness.partialFailure", {
          locked: locked.length,
          total: data.editable_graphs.length,
          error: e instanceof Error ? e.message : String(e),
        })
      );
    } finally {
      setPublishing(false);
      reload();
    }
  };

  return (
    <section data-testid="publication-readiness">
      <header>
        <h1>{t("publication.readiness.title")}</h1>
        <StatusBadge ready={data.ready} />
      </header>
      <ul>
        {data.gates.map((g) => (
          <li key={g.gate} data-gate={g.gate} data-status={g.status}>
            <GateIcon status={g.status} /> {g.label}
          </li>
        ))}
      </ul>
      <section>
        <h2>{t("publication.readiness.editableGraphs")}</h2>
        <ul>
          {data.editable_graphs.map((g) => (
            <li key={g.graph_iri}>{g.graph_iri} ({g.role})</li>
          ))}
        </ul>
      </section>
      {publishError && <div role="alert">{publishError}</div>}
      <button
        onClick={handlePublish}
        disabled={publishing || readOnly || data.editable_graphs.length === 0}
      >
        {t("publication.readiness.publish")}
      </button>
    </section>
  );
}

function StatusBadge({ ready }: { ready: boolean }) {
  return <span data-ready={ready}>{ready ? "Ready" : "Not ready"}</span>;
}

function GateIcon({ status }: { status: "passed" | "warning" | "blocked" }) {
  return <span data-gate-icon={status}>●</span>;
}
```

Adjust the `WorkbenchRequest` import path and `semanticApi` exports to match what's actually exported (check `frontend/src/semanticApi.ts`).

- [ ] **Step C2.2: Verify typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step C2.3: Add i18n keys**

Edit `frontend/src/i18n/zh.ts` and `translations.ts`. Add to the `zh` and `en` blocks respectively:

```typescript
publication: {
  readiness: {
    title: "发布就绪",
    error: "无法获取就绪状态",
    empty: "尚未选择 graph set",
    editableGraphs: "可编辑的图",
    publish: "锁定全部图并导出包",
    partialFailure: "部分图锁定失败 ({{locked}}/{{total}}): {{error}}",
  },
},
```

(English equivalents in `translations.ts`.)

### Task C3: Strip legacy types from `governanceTypes.ts`

**Files:**
- Modify: `frontend/src/pages/governanceTypes.ts`

- [ ] **Step C3.1: Find usages**

Run: `cd frontend && grep -rn "OntologyVersion\|GovernancePageContext" src/`
Expected: only `VersionsPage.tsx` (which is deleted in Phase D) and `PublicationPage.tsx` (now rewritten). Stage 5 governance pages may use `formatTimestamp`/`jsonText`/`messageFrom` — keep those.

- [ ] **Step C3.2: Remove unused exports**

Delete the `OntologyVersion` interface and `GovernancePageContext` from `governanceTypes.ts`. Keep helper functions used elsewhere.

- [ ] **Step C3.3: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): rewrite PublicationPage as graph-set readiness dashboard (Stage 3 §7.1)"
```

---

## Phase D — Frontend `GraphSetHistoryPage`

**Subagent:** `stage3-frontend-history`
**Dependencies:** Phase A + B passing
**Verify gate:** `cd frontend && npm run typecheck && npm run test` pass.

### Task D1: Add `useGraphSetHistory` and `useGraphSetDelta` hooks

**Files:**
- Create: `frontend/src/hooks/useGraphSetHistory.ts`
- Create: `frontend/src/hooks/useGraphSetDelta.ts`

- [ ] **Step D1.1: Write `useGraphSetHistory`**

```typescript
import { useEffect, useState } from "react";
import { readModel, WorkbenchRequest } from "../semanticApi";

export interface GraphSetHistoryEntry {
  graph_set_id: string;
  status: "editable" | "locked" | "superseded";
  created_at: string;
  locked_at: string | null;
  source_signature: string;
  member_count: number;
  latest_derived_pointer_at: string | null;
  ready: boolean | null;
}

export interface GraphSetHistoryEnvelope {
  rows: { graph_sets: GraphSetHistoryEntry[]; total: number };
}

export function useGraphSetHistory(
  request: WorkbenchRequest,
  scopeType: "ontology" | "project",
  scopeId: string | null,
  anchorGraphSetId: string | null
) {
  const [data, setData] = useState<GraphSetHistoryEntry[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!anchorGraphSetId) return;
    setLoading(true);
    readModel<GraphSetHistoryEnvelope>(
      request,
      anchorGraphSetId,
      "graph-set-history-list",
      { field_set: "summary" }
    )
      .then((env) => setData(env.rows.graph_sets))
      .finally(() => setLoading(false));
  }, [request, anchorGraphSetId, scopeType, scopeId]);

  return { data, loading };
}
```

- [ ] **Step D1.2: Write `useGraphSetDelta`**

```typescript
import { useCallback, useState } from "react";
import { readModel, WorkbenchRequest } from "../semanticApi";

export interface TripleDelta {
  subject: string;
  predicate: string;
  object: string;
}

export interface RoleDelta {
  role: string;
  base_graph_iri: string | null;
  target_graph_iri: string | null;
  added: TripleDelta[];
  removed: TripleDelta[];
  counts: { added: number; removed: number };
}

export interface GraphSetDeltaEnvelope {
  rows: {
    base_graph_set_id: string;
    target_graph_set_id: string;
    roles: RoleDelta[];
  };
}

export function useGraphSetDelta(request: WorkbenchRequest) {
  const [data, setData] = useState<RoleDelta[] | null>(null);
  const [loading, setLoading] = useState(false);

  const compute = useCallback(
    async (baseId: string, targetId: string) => {
      setLoading(true);
      try {
        const env = await readModel<GraphSetDeltaEnvelope>(
          request,
          baseId,
          "graph-set-delta",
          { field_set: "detail", target: targetId } as never
        );
        setData(env.rows.roles);
      } finally {
        setLoading(false);
      }
    },
    [request]
  );

  return { data, loading, compute };
}
```

(If `readModel`'s typed params don't accept a free-form `target`, cast to `never` or extend the helper signature in `semanticApi.ts:370`.)

### Task D2: Create `GraphSetHistoryPage.tsx`

**Files:**
- Create: `frontend/src/pages/GraphSetHistoryPage.tsx`
- Delete: `frontend/src/pages/VersionsPage.tsx`

- [ ] **Step D2.1: Write the new page**

```tsx
import { useState } from "react";
import {
  useGraphSetHistory,
  GraphSetHistoryEntry,
} from "../hooks/useGraphSetHistory";
import { useGraphSetDelta } from "../hooks/useGraphSetDelta";
import { WorkbenchRequest } from "../semanticApi";
import { useTranslation } from "react-i18next";

interface Props {
  request: WorkbenchRequest;
  ontologyId: string;
}

export function GraphSetHistoryPage({ request, ontologyId }: Props) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string | null>(null);
  const [baseId, setBaseId] = useState<string>("");
  const [targetId, setTargetId] = useState<string>("");

  // anchorGraphSetId is whatever the parent passes via URL or context.
  // For Stage 3 we re-use the active graph set id; the composer ignores
  // the path id and queries by scope.
  const anchor = selected ?? null;
  const { data: history, loading: historyLoading } = useGraphSetHistory(
    request,
    "ontology",
    ontologyId,
    anchor
  );
  const { data: delta, loading: deltaLoading, compute } = useGraphSetDelta(request);

  return (
    <section data-testid="graph-set-history">
      <header>
        <h1>{t("graphSetHistory.title")}</h1>
      </header>
      <div style={{ display: "flex", gap: 24 }}>
        <ul aria-label="graph-set-list">
          {(history ?? []).map((g) => (
            <li
              key={g.graph_set_id}
              data-selected={selected === g.graph_set_id}
              onClick={() => setSelected(g.graph_set_id)}
            >
              <LockIcon status={g.status} /> {g.graph_set_id}
              <small> {new Date(g.created_at).toLocaleString()}</small>
            </li>
          ))}
          {historyLoading && <li>{t("common.loading")}</li>}
        </ul>
        <section aria-label="detail">
          {selected ? (
            <GraphSetDetail entry={history?.find((g) => g.graph_set_id === selected)!} />
          ) : (
            <p>{t("graphSetHistory.selectPrompt")}</p>
          )}
          <hr />
          <h3>{t("graphSetHistory.diffTitle")}</h3>
          <label>
            {t("graphSetHistory.base")}
            <input value={baseId} onChange={(e) => setBaseId(e.target.value)} />
          </label>
          <label>
            {t("graphSetHistory.target")}
            <input value={targetId} onChange={(e) => setTargetId(e.target.value)} />
          </label>
          <button
            onClick={() => compute(baseId, targetId)}
            disabled={!baseId || !targetId || deltaLoading}
          >
            {t("graphSetHistory.computeDelta")}
          </button>
          {delta && (
            <ul aria-label="delta-roles">
              {delta.map((r) => (
                <li key={r.role}>
                  {r.role}: +{r.counts.added} / -{r.counts.removed}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </section>
  );
}

function GraphSetDetail({ entry }: { entry: GraphSetHistoryEntry }) {
  return (
    <dl>
      <dt>ID</dt><dd>{entry.graph_set_id}</dd>
      <dt>Status</dt><dd>{entry.status}</dd>
      <dt>Members</dt><dd>{entry.member_count}</dd>
      <dt>Latest derived pointer</dt>
      <dd>{entry.latest_derived_pointer_at ?? "—"}</dd>
    </dl>
  );
}

function LockIcon({ status }: { status: string }) {
  return <span data-status={status}>{status === "locked" ? "🔒" : "●"}</span>;
}
```

- [ ] **Step D2.2: Delete `VersionsPage.tsx`**

```bash
git rm frontend/src/pages/VersionsPage.tsx
```

- [ ] **Step D2.3: Add i18n keys**

```typescript
graphSetHistory: {
  title: "Graph Set 历史",
  selectPrompt: "选择左侧的 graph set 查看详情",
  diffTitle: "Diff",
  base: "Base",
  target: "Target",
  computeDelta: "计算 delta",
},
```

- [ ] **Step D2.4: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): replace VersionsPage with GraphSetHistoryPage (Stage 3 §7.2)"
```

---

## Phase E — Frontend Wiring

**Subagent:** `stage3-frontend-wiring`
**Dependencies:** Phase C + D passing
**Verify gate:** `cd frontend && npm run typecheck && npm run build` pass; manual smoke `npm run dev` shows both new pages.

### Task E1: Update `App.tsx` routing, tabs, and lock guard

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step E1.1: Rename tab id**

Replace `"versions"` with `"graph-set-history"` in:
- Tab catalog (around `:131`)
- Stage mapping (`:196`): `publish: "graph-set-history"` instead of `publish: "publication"` (or whatever the existing convention is — match it)
- Sidebar nav entries (`:225-226`)
- Lazy Stage2 FactAuditPage swap (`:1051-1067`) — simplify; no more conditional PublicationPage fallback

- [ ] **Step E1.2: Remove the lock-guard exception**

Delete the regex `/^\/versions\/[^/]+\/mutability$/` and its surrounding condition (`:1030-1032`).

- [ ] **Step E3.3: Update imports**

Remove `VersionsPage` import (`:104`). Add `GraphSetHistoryPage` import. Keep `PublicationPage` import.

- [ ] **Step E1.4: Update routes**

In the route table, replace the `versions` route's `element={<VersionsPage ... />}` with `<GraphSetHistoryPage ... />`.

- [ ] **Step E1.5: Update `BuildOverviewPage` callbacks**

In `App.tsx:1040` and `PublicationPage.tsx:151`, remove any `versions` references. Replace with `graph-set-history` where applicable.

- [ ] **Step E1.6: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

### Task E2: Strip legacy i18n keys

**Files:**
- Modify: `frontend/src/i18n/zh.ts`
- Modify: `frontend/src/i18n/translations.ts`

- [ ] **Step E2.1: Remove obsolete keys**

Delete (across both files):
- All keys under `versions.*`
- All keys under `mutability.*`
- All keys under `proposals.*`
- Legacy `publication.gate.*` keys (the new keys live under `publication.readiness.*`)

- [ ] **Step E2.2: Verify no dangling references**

Run: `cd frontend && grep -rn "t(['\"]versions\\." src/`
Expected: no hits. Same for `mutability.` and `proposals.`.

### Task E3: Patch `BuildOverviewPage` if it referenced version endpoints

**Files:**
- Possibly modify: `frontend/src/pages/BuildOverviewPage.tsx`

- [ ] **Step E3.1: Search for legacy endpoint references**

Run: `cd frontend && grep -n "ontologies/.*/versions\|/versions/\|/proposals\|/publication-readiness" src/pages/BuildOverviewPage.tsx`
Expected: no hits if Stage 1 already migrated. If hits exist, replace with the new read-model call (`graph-set-history-list` or `publication-readiness`).

- [ ] **Step E3.2: Typecheck and build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step E3.3: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): rewire App.tsx routes and tabs for Stage 3 (§7.3, §7.4)"
```

---

## Phase F — Playwright e2e

**Subagent:** `stage3-tests-e2e`
**Dependencies:** Phase E passing
**Verify gate:** `cd frontend && npx playwright test stage3-publish.spec.ts` passes; full Playwright suite green.

### Task F1: Write `stage3-publish.spec.ts`

**Files:**
- Create: `frontend/tests/stage3-publish.spec.ts`

- [ ] **Step F1.1: Write the spec**

```typescript
import { test, expect } from "@playwright/test";
import { API_BASE_URL, SEMANTIC_BASE } from "../src/semanticApi";

const GRAPH_SET_ID = "gs-stage3-smoke";
const ONTOLOGY_GRAPH = "http://op.local/semantic/graph/ontology/acme";
const DATA_GRAPH = "http://op.local/semantic/graph/data/acme";

test.beforeEach(async ({ page }) => {
  await page.route(`${SEMANTIC_BASE}/graph-sets/${GRAPH_SET_ID}/read-models/publication-readiness**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        graph_set_id: GRAPH_SET_ID,
        projection_name: "publication-readiness",
        projection_version: "1",
        field_set: "detail",
        rows: [{
          graph_set_id: GRAPH_SET_ID,
          ready: false,
          gates: [
            { gate: "validation_stale", status: "passed", label: "validation fresh", details: {} },
            { gate: "reasoning_stale", status: "passed", label: "reasoning fresh", details: {} },
            { gate: "rule_stale", status: "warning", label: "rule 3d old", details: {} },
            { gate: "missing_evidence", status: "passed", label: "0 facts missing", details: { count: 0 } },
            { gate: "open_edits", status: "warning", label: "2 pending edits", details: { count: 2 } },
            { gate: "projection_freshness", status: "passed", label: "projections fresh", details: {} },
          ],
          blockers: [],
          warnings: ["rule 3d old", "2 pending edits"],
          editable_graph_count: 2,
          editable_graphs: [
            { graph_iri: ONTOLOGY_GRAPH, role: "asserted_ontology" },
            { graph_iri: DATA_GRAPH, role: "asserted_data" },
          ],
          last_published_at: null,
        }],
      }),
    });
  });
});

test("renders all gates", async ({ page }) => {
  await page.goto(`/workbench?graphSet=${GRAPH_SET_ID}&tab=publication`);
  await expect(page.locator('[data-testid="publication-readiness"]')).toBeVisible();
  await expect(page.locator('[data-gate="validation_stale"]')).toBeVisible();
  await expect(page.locator('[data-gate="rule_stale"][data-status="warning"]')).toBeVisible();
  await expect(page.locator('[data-gate="open_edits"][data-status="warning"]')).toBeVisible();
});

test("publish fires editability + export", async ({ page }) => {
  let lockedCount = 0;
  await page.route(`${SEMANTIC_BASE}/graphs/*/editability`, async (route) => {
    if (route.request().method() === "PATCH") {
      lockedCount += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    } else {
      await route.continue();
    }
  });
  await page.route(`${SEMANTIC_BASE}/graph-sets/${GRAPH_SET_ID}/export**`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/octet-stream", body: "" });
  });
  await page.goto(`/workbench?graphSet=${GRAPH_SET_ID}&tab=publication`);
  await page.click('button:has-text("Lock all")');
  await page.waitForResponse((r) => r.url().includes("/export"));
  expect(lockedCount).toBe(2);
});
```

Adjust the URL pattern to match the actual frontend route (`/workbench` vs whatever App.tsx mounts).

- [ ] **Step F1.2: Run**

Run: `cd frontend && npx playwright test stage3-publish.spec.ts`
Expected: PASS.

### Task F2: Update existing specs that mock legacy endpoints

**Files:**
- Modify: `frontend/tests/workbench-smoke.spec.ts` (`:300-322,407-412`)
- Modify: `frontend/tests/semantic-governance.spec.ts` (`:201`)
- Modify: `frontend/tests/stage2-graph-derived.spec.ts` (`:196`)
- Modify: `frontend/tests/language-switch.spec.ts` (`:48`)

- [ ] **Step F2.1: Replace each `/ontologies/{id}/versions` mock**

For each spec, replace any `page.route('**/ontologies/*/versions**', ...)` with the appropriate semantic mock:
- For routes that need a list: mock `${SEMANTIC_BASE}/graph-sets/{id}/read-models/graph-set-history-list`
- For routes that need readiness: mock `${SEMANTIC_BASE}/graph-sets/{id}/read-models/publication-readiness`

- [ ] **Step F2.2: Remove the "publication mutability switch locks the current version" test**

`workbench-smoke.spec.ts:407-412` — the test asserts legacy behavior that no longer exists. Delete it.

- [ ] **Step F2.3: Run the full Playwright suite**

Run: `cd frontend && npx playwright test`
Expected: PASS.

- [ ] **Step F2.4: Commit**

```bash
git add frontend/tests/
git commit -m "test(frontend): Stage 3 Playwright coverage and legacy mock cleanup"
```

---

## Phase G — Cleanup Sweep

**Subagent:** `stage3-cleanup`
**Dependencies:** Phase F passing
**Verify gate:** `uv run pytest backend/tests/ -x` and `cd frontend && npm run typecheck && npm run test && npx playwright test` all pass.

### Task G1: Grep for stragglers

**Files:** any

- [ ] **Step G1.1: Grep**

Run each command; expected zero hits (or only doc links):

```bash
grep -rn "ontology_versions\|OntologyVersion" backend/ frontend/ --include='*.py' --include='*.ts' --include='*.tsx' | grep -v '^docs/'
grep -rn "/versions/.*publication-readiness\|/versions/.*/mutability\|/versions/.*/publish" backend/ frontend/
grep -rn "publication-readiness\b" backend/ frontend/ | grep -v '^docs/' | grep -v 'semantic_read_model' | grep -v 'test_semantic_stage3'
grep -rn "OntologyVersionRead\|VersionMutabilityUpdate\|ProposalRead\|ProposalCreate\|VersionDiffRead\|PublicationReadinessRead\|PublicationConfirm\|KnowledgeConflictRead" backend/
grep -rn "ProposalModel\|PublicationGateModel\|OntologyVersionModel\|ReviewBatchModel\|EvidenceModel\|ReviewDecisionModel\|ValidationRunModel\|FactClaimModel\|RuleDefinitionModel\|UnanchoredKnowledgeModel\|KnowledgeConflictModel" backend/
```

- [ ] **Step G1.2: Fix any hits**

Each hit is either:
- A real leftover → delete or rewrite
- A reference inside a docstring/comment → leave if informational, delete if misleading

### Task G2: Full test suite

- [ ] **Step G2.1: Backend**

Run: `uv run pytest backend/tests/ -x`
Expected: PASS.

- [ ] **Step G2.2: Frontend**

Run: `cd frontend && npm run typecheck && npm run test && npx playwright test`
Expected: PASS.

- [ ] **Step G2.3: Commit any stragglers**

```bash
git add -A
git commit -m "chore(semantic): Stage 3 final cleanup sweep"
```

### Task G3: Update spec status

**Files:**
- Modify: `docs/delivery/designs/2026-07-06-semantic-stage3-publish-design.md`

- [ ] **Step G3.1: Flip status**

Change `**Status:** Draft` to `**Status:** Implemented`.

- [ ] **Step G3.2: Commit**

```bash
git add docs/delivery/designs/2026-07-06-semantic-stage3-publish-design.md
git commit -m "docs(semantic): mark Stage 3 spec as implemented"
```

---

## Self-Review Notes

### Spec coverage map

| Spec section | Tasks |
| --- | --- |
| §4.1 `publication-readiness` | A1 |
| §4.2 `graph-set-history-list` | A2 |
| §4.3 `graph-set-delta` | A3 |
| §6.1 router deletions | B1 |
| §6.2 service deletions | B2 |
| §6.3 schema deletions | B3 |
| §6.4 model deletions | B4 |
| §6.5 migration | B5 |
| §6.6 MCP deletions | B6 |
| §6.7 test deletions | B7 |
| §7.1 PublicationPage | C1, C2, C3 |
| §7.2 GraphSetHistoryPage | D1, D2 |
| §7.3 routing | E1, E3 |
| §7.4 i18n | E2 |
| §9 testing | F1, F2 |
| §11 e2e | A4, A5 |

All 16 spec sections mapped.

### Type consistency check

- `PublicationGate` shape in `useGraphSetReadiness.ts` matches §4.1 `GateStatus` (gate/status/details/label). ✓
- `editable_graphs: {graph_iri, role}[]` matches §4.1 row contract. ✓
- `RoleDelta` fields in `useGraphSetDelta.ts` match §4.3 spec. ✓
- `GraphSetHistoryEntry` matches §4.2. ✓
- Composer names `_compose_publication_readiness`, `_compose_graph_set_history_list`, `_compose_graph_set_delta` consistent across §4 spec and plan. ✓

### Placeholder scan

No TBD/TODO/FIXME in tasks. Open questions from spec §13 are flagged in-task where relevant (BuildOverviewPage in E3, ontologies.status in B4 — verify by grep at deletion time).

### Known risks flagged in plan

- **B5 migration constraint names**: if Alembic naming convention differs from `ontologies_current_version_id_fkey`, the drop fails. Plan flags this; SA must verify constraint name before run.
- **A3 RDF store signature**: `_role_triples` uses `self._rdf_store.construct()` and `.select()`. If `RdfStoreRepository` exposes these differently, adapt. Plan tells the SA to confirm by reading the file.
- **E3 BuildOverviewPage**: Stage 1 disposition was **P** (projection-bridge). The plan handles both cases (no-op if already migrated, patch if not).
