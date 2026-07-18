# Semantic Phase 6 — Graph-Derived Product APIs and Projections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make product reads, exports, traversal, search, and vector retrieval derive from RDF graph sets so the platform proves projection parity before the Phase 7 canonical migration.

**Architecture:** Phase 6 adds a graph-derived read/projection layer beside the existing product services. It resolves a graph set, includes current reasoning/rule result graphs via derived-result pointers, queries Oxigraph, and returns compact business JSON, JSON-LD, Turtle/TriG exports, and rebuildable Neo4j/search/vector projections — all carrying provenance, evidence status, assertion kind, and staleness metadata.

**Tech Stack:** FastAPI, SQLAlchemy + Postgres, rdflib, Oxigraph (RdfStoreRepository), Neo4j driver (optional, partition-scoped), pydantic v2, pytest. Tests must NOT require live Oxigraph/Neo4j/search/vector/embedding services — fake adapters only.

**Source spec:** `docs/architecture/semantic/phase6-graph-derived-product-apis-projections.md`

---

## File Structure

**New files:**

| File | Responsibility |
| --- | --- |
| `backend/app/services/semantic_read_scope.py` | `SemanticReadScopeResolver` — turns graph_set_id + `include` parameter into a list of source graph IRIs, derived-result graph IRIs, derived state descriptor, and warnings. |
| `backend/app/services/semantic_read_model.py` | `SemanticReadModelService` — versioned SPARQL templates + bounded query execution + origin/evidence/provenance/staleness decoration. |
| `backend/app/services/semantic_export.py` | (exists) Extended with `SemanticExportService` for graph-set Turtle/TriG/JSON-LD export. |
| `backend/app/services/semantic_projection_job.py` | `SemanticProjectionJobService` — job lifecycle (create/run/list/get), input snapshotting, manifest updates, reconciliation. |
| `backend/app/services/semantic_neo4j_projection.py` | `Neo4jSemanticProjectionService` — partition-scoped node/relationship writer with verification and manifest promotion. |
| `backend/app/services/semantic_search_projection.py` | `SemanticSearchProjectionService` — search document builder + writer interface. |
| `backend/app/services/semantic_vector_projection.py` | `SemanticVectorProjectionService` — vector document builder + embedding config hash + writer interface. |
| `backend/app/services/semantic_visibility.py` | `SemanticVisibilityPolicy` — light label/redaction layer for read models, exports, search, vector docs. |
| `backend/app/services/semantic_sparql_templates.py` | Versioned SPARQL template registry for read models. |
| `backend/migrations/versions/0015_semantic_projection_manifests.py` | Migration: extend `semantic_projection_jobs`, add `semantic_projection_manifests`. |
| `backend/tests/test_semantic_read_scope.py` | Tests for read scope resolver. |
| `backend/tests/test_semantic_read_model.py` | Tests for read-model service and templates. |
| `backend/tests/test_semantic_export_graph_set.py` | Tests for graph-set export service. |
| `backend/tests/test_semantic_projection_job.py` | Tests for projection jobs, manifests, and reconciliation. |
| `backend/tests/test_semantic_neo4j_projection.py` | Tests for partition-scoped Neo4j writer. |
| `backend/tests/test_semantic_search_projection.py` | Tests for search document builder. |
| `backend/tests/test_semantic_vector_projection.py` | Tests for vector document builder. |
| `backend/tests/test_semantic_visibility.py` | Tests for visibility policy. |
| `backend/tests/test_semantic_phase6_api.py` | API tests for read models, resources, statements, export, projection jobs, projection status. |

**Modified files:**

| File | Change |
| --- | --- |
| `backend/app/repositories/models.py` | Extend `SemanticProjectionJobModel` with new columns; add `SemanticProjectionManifestModel`. |
| `backend/app/api/schemas.py` | Add read-model envelope/item schemas, projection job/manifest schemas, export request schema. |
| `backend/app/api/semantic.py` | Add new routes: read-models, resources, statements, graph-set export, projection jobs (CRUD), projection reconcile/status. Extend `_service` factories. |
| `backend/app/mcp/tools/semantic.py` | Add 5 new MCP tools. |
| `backend/tests/test_mcp_surface.py` | Update expected MCP tool surface. |
| `backend/tests/test_semantic_api.py` | Update for new routes / extended projection response model. |
| `semantic-language-refactor-plan.md` | Update progress marker for Phase 6 completion. |

---

## Task 1: Read Scope Resolver

Resolve `include=asserted|asserted-plus-reasoning|asserted-plus-rules|full-working-view` against a graph set into concrete graph IRIs and a derived-state descriptor.

**Files:**
- Create: `backend/app/services/semantic_read_scope.py`
- Test: `backend/tests/test_semantic_read_scope.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_semantic_read_scope.py
from datetime import UTC, datetime

from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)
from app.services.semantic_read_scope import (
    ReadScopeError,
    SemanticReadScopeResolver,
    ScopeResolution,
)


def _make_graph_set(session, members):
    gs = SemanticGraphSetModel(
        id="gs-1",
        name="demo",
        scope_type="ontology_version",
        scope_id="ov-1",
        status="active",
        source_signature="sig-1",
    )
    session.add(gs)
    for idx, (iri, role) in enumerate(members):
        gs.members.append(
            SemanticGraphSetMemberModel(
                id=f"m-{idx}",
                graph_iri=iri,
                role=role,
                required=True,
                sort_order=idx,
            )
        )
    session.commit()
    return gs


def _add_pointer(session, kind, status="current", iri="http://x/reasoning-result/run-1"):
    session.add(
        SemanticDerivedResultPointerModel(
            id=f"ptr-{kind}",
            graph_set_id="gs-1",
            result_kind=kind,
            run_id=f"run-{kind}",
            result_graph_iri=iri,
            source_signature="sig-1",
            status=status,
            became_current_at=datetime.now(UTC),
        )
    )
    session.commit()


def test_asserted_scope_returns_only_source_graphs(session_factory):
    with session_factory() as session:
        _make_graph_set(
            session,
            [
                ("http://op/s/graph/ontology/ov-1", "asserted_ontology"),
                ("http://op/s/graph/data/ov-1", "asserted_data"),
                ("http://op/s/graph/shapes/ov-1", "shape"),
            ]
        )
        resolver = SemanticReadScopeResolver(session)
        result = resolver.resolve("gs-1", include="asserted")
        assert isinstance(result, ScopeResolution)
        assert set(result.source_graph_iris) == {
            "http://op/s/graph/ontology/ov-1",
            "http://op/s/graph/data/ov-1",
        }
        assert result.shape_graph_iris == ["http://op/s/graph/shapes/ov-1"]
        assert result.reasoning_result_graph_iri is None
        assert result.rule_result_graph_iri is None


def test_asserted_plus_reasoning_includes_current_pointer(session_factory):
    with session_factory() as session:
        _make_graph_set(
            session,
            [("http://op/s/graph/ontology/ov-1", "asserted_ontology")],
        )
        _add_pointer(session, "reasoning")
        resolver = SemanticReadScopeResolver(session)
        result = resolver.resolve("gs-1", include="asserted-plus-reasoning")
        assert result.reasoning_result_graph_iri == "http://x/reasoning-result/run-1"
        assert result.rule_result_graph_iri is None


def test_full_working_view_includes_all_current_pointers(session_factory):
    with session_factory() as session:
        _make_graph_set(
            session,
            [("http://op/s/graph/data/ov-1", "asserted_data")],
        )
        _add_pointer(session, "reasoning", iri="http://x/rr/run-1")
        _add_pointer(session, "rule", iri="http://x/rl/run-1")
        resolver = SemanticReadScopeResolver(session)
        result = resolver.resolve("gs-1", include="full-working-view")
        assert result.reasoning_result_graph_iri == "http://x/rr/run-1"
        assert result.rule_result_graph_iri == "http://x/rl/run-1"


def test_stale_pointer_with_allow_stale_false_raises(session_factory):
    with session_factory() as session:
        _make_graph_set(
            session,
            [("http://op/s/graph/data/ov-1", "asserted_data")],
        )
        _add_pointer(session, "reasoning", status="stale")
        resolver = SemanticReadScopeResolver(session)
        try:
            resolver.resolve("gs-1", include="asserted-plus-reasoning", allow_stale_derived=False)
            raise AssertionError("expected ReadScopeError")
        except ReadScopeError as exc:
            assert "stale" in str(exc).lower()


def test_stale_pointer_with_allow_stale_true_produces_warning(session_factory):
    with session_factory() as session:
        _make_graph_set(
            session,
            [("http://op/s/graph/data/ov-1", "asserted_data")],
        )
        _add_pointer(session, "reasoning", status="stale")
        resolver = SemanticReadScopeResolver(session)
        result = resolver.resolve("gs-1", include="asserted-plus-reasoning", allow_stale_derived=True)
        assert result.reasoning_result_graph_iri == "http://x/reasoning-result/run-1"
        assert any(w["code"] == "stale_reasoning_result" for w in result.warnings)


def test_missing_pointer_for_required_scope_warns(session_factory):
    with session_factory() as session:
        _make_graph_set(
            session,
            [("http://op/s/graph/data/ov-1", "asserted_data")],
        )
        # no pointers seeded
        resolver = SemanticReadScopeResolver(session)
        result = resolver.resolve("gs-1", include="asserted-plus-rules", allow_stale_derived=True)
        assert result.rule_result_graph_iri is None
        assert any(w["code"] == "missing_rule_result" for w in result.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_semantic_read_scope.py -v
```

Expected: collection error — `semantic_read_scope` module does not exist.

- [ ] **Step 3: Implement read scope resolver**

```python
# backend/app/services/semantic_read_scope.py
"""Resolve a graph set + include parameter into concrete graph IRIs and derived state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)


class ReadScopeError(RuntimeError):
    status_code = 400


_VALID_INCLUDES = {
    "asserted",
    "asserted-plus-reasoning",
    "asserted-plus-rules",
    "full-working-view",
}

_SOURCE_ROLES = {"asserted_ontology", "asserted_data"}
_GOVERNANCE_ROLES = {"evidence", "shape", "policy"}


@dataclass
class ScopeResolution:
    graph_set_id: str
    source_signature: str
    include: str
    source_graph_iris: list[str]
    shape_graph_iris: list[str]
    governance_graph_iris: list[str]
    reasoning_result_graph_iri: str | None
    rule_result_graph_iri: str | None
    derived_state: dict[str, Any]
    warnings: list[dict[str, str]] = field(default_factory=list)


class SemanticReadScopeResolver:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve(
        self,
        graph_set_id: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
    ) -> ScopeResolution:
        if include not in _VALID_INCLUDES:
            raise ReadScopeError(f"Unsupported include value: {include}")
        graph_set = self._get_graph_set(graph_set_id)
        members = self._members(graph_set_id)
        source_iris = [m.graph_iri for m in members if m.role in _SOURCE_ROLES]
        shape_iris = [m.graph_iri for m in members if m.role == "shape"]
        governance_iris = [m.graph_iri for m in members if m.role in _GOVERNANCE_ROLES and m.role != "shape"]

        pointers = self._current_pointers(graph_set_id)
        warnings: list[dict[str, str]] = []
        reasoning_iri = None
        rule_iri = None

        if include in {"asserted-plus-reasoning", "full-working-view"}:
            reasoning_iri, warning = self._resolve_pointer(pointers, "reasoning", allow_stale_derived)
            if warning:
                warnings.append(warning)

        if include in {"asserted-plus-rules", "full-working-view"}:
            rule_iri, warning = self._resolve_pointer(pointers, "rule", allow_stale_derived)
            if warning:
                warnings.append(warning)

        derived_state = {
            "reasoning": self._derived_descriptor(pointers.get("reasoning")),
            "rule": self._derived_descriptor(pointers.get("rule")),
        }

        return ScopeResolution(
            graph_set_id=graph_set_id,
            source_signature=graph_set.source_signature,
            include=include,
            source_graph_iris=source_iris,
            shape_graph_iris=shape_iris,
            governance_graph_iris=governance_iris,
            reasoning_result_graph_iri=reasoning_iri,
            rule_result_graph_iri=rule_iri,
            derived_state=derived_state,
            warnings=warnings,
        )

    def _get_graph_set(self, graph_set_id: str) -> SemanticGraphSetModel:
        record = self.session.scalar(
            select(SemanticGraphSetModel).where(SemanticGraphSetModel.id == graph_set_id)
        )
        if record is None:
            raise ReadScopeError(f"Graph set not found: {graph_set_id}")
        return record

    def _members(self, graph_set_id: str) -> list[SemanticGraphSetMemberModel]:
        return list(
            self.session.scalars(
                select(SemanticGraphSetMemberModel)
                .where(SemanticGraphSetMemberModel.graph_set_id == graph_set_id)
                .order_by(SemanticGraphSetMemberModel.sort_order)
            )
        )

    def _current_pointers(self, graph_set_id: str) -> dict[str, SemanticDerivedResultPointerModel]:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.graph_set_id == graph_set_id
            )
        )
        return {row.result_kind: row for row in rows}

    def _resolve_pointer(
        self,
        pointers: dict[str, SemanticDerivedResultPointerModel],
        kind: str,
        allow_stale: bool,
    ) -> tuple[str | None, dict[str, str] | None]:
        pointer = pointers.get(kind)
        if pointer is None:
            return None, {"code": f"missing_{kind}_result", "message": f"No current {kind} result pointer."}
        if pointer.status == "stale":
            if not allow_stale:
                raise ReadScopeError(f"{kind} result pointer is stale for this graph set")
            return pointer.result_graph_iri, {
                "code": f"stale_{kind}_result",
                "message": f"{kind.capitalize()}-derived statements are stale for this graph set.",
            }
        return pointer.result_graph_iri, None

    def _derived_descriptor(self, pointer: SemanticDerivedResultPointerModel | None) -> dict[str, Any]:
        if pointer is None:
            return {"status": "missing", "run_id": None, "result_graph_iri": None}
        return {
            "status": pointer.status,
            "run_id": pointer.run_id,
            "result_graph_iri": pointer.result_graph_iri,
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_semantic_read_scope.py -v
```

Expected: 6 passing tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_read_scope.py backend/tests/test_semantic_read_scope.py
git commit -m "Add semantic phase 6 read scope resolver"
```

---

## Task 2: Migration 0015 — Projection Job Extensions and Manifests

Extend `semantic_projection_jobs` with graph-set-aware fields and add `semantic_projection_manifests`.

**Files:**
- Modify: `backend/app/repositories/models.py`
- Create: `backend/migrations/versions/0015_semantic_projection_manifests.py`

- [ ] **Step 1: Extend the SQLAlchemy models**

In `backend/app/repositories/models.py`, locate `class SemanticProjectionJobModel` (around line 907) and replace its body with:

```python
class SemanticProjectionJobModel(Base):
    __tablename__ = "semantic_projection_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_set_id: Mapped[str | None] = mapped_column(String(36))
    projection_kind: Mapped[str] = mapped_column(String(40), default="neo4j", nullable=False)
    projection_version: Mapped[str] = mapped_column(String(80), default="neo4j-v1", nullable=False)
    projection_scope: Mapped[str] = mapped_column(
        String(40), default="asserted", nullable=False
    )
    source_graph_iris: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    reasoning_result_graph_iri: Mapped[str | None] = mapped_column(Text)
    rule_result_graph_iri: Mapped[str | None] = mapped_column(Text)
    source_signature: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    input_graph_revisions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    input_derived_pointers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    target_store: Mapped[str | None] = mapped_column(String(80))
    target_partition: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    job_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
```

Append a new model class at the end of the semantic block (after `SemanticRuleRunModel`):

```python
class SemanticProjectionManifestModel(Base):
    __tablename__ = "semantic_projection_manifests"
    __table_args__ = (
        UniqueConstraint(
            "graph_set_id",
            "projection_kind",
            "target_partition",
            name="uq_semantic_projection_manifests_set_kind_partition",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_set_id: Mapped[str] = mapped_column(String(36), nullable=False)
    projection_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    active_job_id: Mapped[str | None] = mapped_column(String(36))
    source_signature: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    projection_version: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    target_partition: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="current", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    manifest_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
```

- [ ] **Step 2: Write migration 0015**

```python
# backend/migrations/versions/0015_semantic_projection_manifests.py
"""semantic projection manifests and graph-set-aware jobs

Revision ID: 0015_semantic_projection_manifests
Revises: 0014_semantic_rule_tables
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_semantic_projection_manifests"
down_revision = "0014_semantic_rule_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("semantic_projection_jobs", sa.Column("graph_set_id", sa.String(length=36), nullable=True))
    op.add_column("semantic_projection_jobs", sa.Column("projection_kind", sa.String(length=40), nullable=False, server_default="neo4j"))
    op.add_column("semantic_projection_jobs", sa.Column("projection_version", sa.String(length=80), nullable=False, server_default="neo4j-v1"))
    op.add_column("semantic_projection_jobs", sa.Column("projection_scope", sa.String(length=40), nullable=False, server_default="asserted"))
    op.add_column("semantic_projection_jobs", sa.Column("source_signature", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("semantic_projection_jobs", sa.Column("input_graph_revisions", sa.JSON, nullable=False, server_default="{}"))
    op.add_column("semantic_projection_jobs", sa.Column("input_derived_pointers", sa.JSON, nullable=False, server_default="{}"))
    op.add_column("semantic_projection_jobs", sa.Column("target_store", sa.String(length=80), nullable=True))
    op.add_column("semantic_projection_jobs", sa.Column("target_partition", sa.String(length=255), nullable=True))
    op.add_column("semantic_projection_jobs", sa.Column("rule_result_graph_iri", sa.Text(), nullable=True))
    op.add_column("semantic_projection_jobs", sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "semantic_projection_manifests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_set_id", sa.String(length=36), nullable=False),
        sa.Column("projection_kind", sa.String(length=40), nullable=False),
        sa.Column("active_job_id", sa.String(length=36), nullable=True),
        sa.Column("source_signature", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("projection_version", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("target_partition", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="current"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "graph_set_id",
            "projection_kind",
            "target_partition",
            name="uq_semantic_projection_manifests_set_kind_partition",
        ),
    )


def downgrade() -> None:
    op.drop_table("semantic_projection_manifests")
    for col in (
        "document_count",
        "rule_result_graph_iri",
        "target_partition",
        "target_store",
        "input_derived_pointers",
        "input_graph_revisions",
        "source_signature",
        "projection_scope",
        "projection_version",
        "projection_kind",
        "graph_set_id",
    ):
        op.drop_column("semantic_projection_jobs", col)
```

- [ ] **Step 3: Verify migration applies cleanly**

```bash
cd backend && uv run alembic upgrade head
```

Expected: `0015_semantic_projection_manifests` is the head; no SQL errors.

- [ ] **Step 4: Verify existing tests still pass**

```bash
cd backend && uv run pytest tests/test_semantic_projection.py tests/test_semantic_api.py -x
```

Expected: existing tests still pass against the extended model.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/models.py backend/migrations/versions/0015_semantic_projection_manifests.py
git commit -m "Extend semantic projection job model and add projection manifests"
```

---

## Task 3: Pydantic Schemas for Read Models, Exports, Projection Jobs

**Files:**
- Modify: `backend/app/api/schemas.py`

- [ ] **Step 1: Add read-model and projection-job schemas**

Append to `backend/app/api/schemas.py` (in the semantic block):

```python
class SemanticReadModelEnvelope(BaseModel):
    graph_set_id: str
    source_signature: str
    projection_version: str
    include: str
    derived_state: dict[str, Any]
    warnings: list[dict[str, str]] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)


class SemanticStatementItem(BaseModel):
    id: str
    iri: str
    label: str | None = None
    source_graph_iri: str
    assertion_kind: str
    evidence_status: str
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: dict[str, Any]
    audit_status: str | None = None
    staleness: dict[str, Any]


class SemanticResourceRead(BaseModel):
    iri: str
    label: str | None = None
    graph_set_id: str | None = None
    source_signature: str | None = None
    assertion_kind: str
    evidence_status: str
    source_graph_iri: str
    properties: dict[str, Any] = Field(default_factory=dict)
    derived_state: dict[str, Any] = Field(default_factory=dict)
    warnings: list[dict[str, str]] = Field(default_factory=list)


class SemanticExportRequest(BaseModel):
    format: Literal["trig", "turtle", "json-ld"] = "trig"
    include: Literal[
        "asserted",
        "asserted-plus-reasoning",
        "asserted-plus-rules",
        "full-working-view",
    ] = "asserted"
    include_evidence: bool = False
    include_shapes: bool = False
    include_policy: bool = False
    include_metadata: bool = False
    allow_stale_derived: bool = False
    visibility_context: dict[str, Any] | None = None


class SemanticProjectionJobCreate(BaseModel):
    graph_set_id: str
    projection_kind: Literal["business_json", "neo4j", "search", "vector", "export_cache"]
    projection_version: str
    include: Literal[
        "asserted",
        "asserted-plus-reasoning",
        "asserted-plus-rules",
        "full-working-view",
    ] = "asserted"
    allow_stale_derived: bool = False
    mode: Literal["dry_run", "rebuild", "rebuild_side_by_side", "reconcile"] = "rebuild"
    target_partition: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticProjectionJobRead(BaseModel):
    id: str
    graph_set_id: str | None
    projection_kind: str
    projection_version: str
    projection_scope: str
    source_signature: str
    input_graph_revisions: dict[str, Any]
    input_derived_pointers: dict[str, Any]
    target_store: str | None
    target_partition: str | None
    status: str
    node_count: int
    relationship_count: int
    document_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SemanticProjectionJobListResponse(BaseModel):
    items: list[SemanticProjectionJobRead]
    total: int


class SemanticProjectionManifestRead(BaseModel):
    id: str
    graph_set_id: str
    projection_kind: str
    active_job_id: str | None
    source_signature: str
    projection_version: str
    target_partition: str
    status: str
    updated_at: datetime
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SemanticProjectionStatusResponse(BaseModel):
    manifests: list[SemanticProjectionManifestRead]
    stale: list[str]
    missing: list[str]


class SemanticProjectionReconcileResponse(BaseModel):
    reconciled: int
    marked_stale: list[str]
    warnings: list[dict[str, str]] = Field(default_factory=list)
```

Locate the existing `SemanticProjectionResponse` class and leave it intact for backward compatibility with the existing `/projection-jobs` POST.

- [ ] **Step 2: Verify schemas import cleanly**

```bash
cd backend && uv run python -c "from app.api.schemas import SemanticReadModelEnvelope, SemanticProjectionJobCreate, SemanticProjectionManifestRead; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/schemas.py
git commit -m "Add semantic phase 6 read model and projection job schemas"
```

---

## Task 4: SPARQL Template Registry and Read-Model Service

**Files:**
- Create: `backend/app/services/semantic_sparql_templates.py`
- Create: `backend/app/services/semantic_read_model.py`
- Test: `backend/tests/test_semantic_read_model.py`

- [ ] **Step 1: Write failing test for read-model service**

```python
# backend/tests/test_semantic_read_model.py
from app.services.semantic_read_model import SemanticReadModelService, ReadModelError


class FakeSparqlResult:
    def __init__(self, rows):
        self.rows = rows

    @property
    def bindings(self):
        return self.rows


class FakeStore:
    def __init__(self, rows_by_template: dict[str, list[dict[str, str]]]):
        self.rows_by_template = rows_by_template
        self.last_query = None
        self.last_graph_iris = None

    def query_read_model(self, query, graph_iris, timeout_seconds, limit):
        self.last_query = query
        self.last_graph_iris = list(graph_iris)
        # Match by template marker embedded in query text
        for marker, rows in self.rows_by_template.items():
            if marker in query:
                return FakeSparqlResult(rows)
        return FakeSparqlResult([])


class FakeScopeResolver:
    def __init__(self, resolution):
        self._resolution = resolution

    def resolve(self, graph_set_id, include="asserted", allow_stale_derived=True):
        return self._resolution


def _resolution(graph_iris, reasoning=None, rule=None, signature="sig-1"):
    from app.services.semantic_read_scope import ScopeResolution
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature=signature,
        include="asserted",
        source_graph_iris=graph_iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=reasoning,
        rule_result_graph_iri=rule,
        derived_state={},
        warnings=[],
    )


def test_schema_summary_returns_envelope_with_origin_metadata():
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/ontology/ov-1"]))
    store = FakeStore({
        "schema-summary": [
            {"class": "http://op/s/class/student", "label": "Student", "graph": "http://op/s/graph/ontology/ov-1"},
            {"class": "http://op/s/class/course", "label": "Course", "graph": "http://op/s/graph/ontology/ov-1"},
        ]
    })
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
    envelope = service.read_model("gs-1", "ontology-schema-summary", include="asserted")
    assert envelope["graph_set_id"] == "gs-1"
    assert envelope["source_signature"] == "sig-1"
    assert envelope["projection_version"].startswith("semantic-read-v")
    assert len(envelope["items"]) == 2
    item = envelope["items"][0]
    assert item["assertion_kind"] == "asserted"
    assert item["source_graph_iri"] == "http://op/s/graph/ontology/ov-1"
    assert item["evidence_status"] == "not_applicable"
    assert "staleness" in item


def test_unknown_model_raises():
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/data/ov-1"]))
    store = FakeStore({})
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
    try:
        service.read_model("gs-1", "no-such-model")
        raise AssertionError("expected ReadModelError")
    except ReadModelError as exc:
        assert "no-such-model" in str(exc)


def test_full_working_view_includes_reasoning_and_rule_graphs():
    resolver = FakeScopeResolver(
        _resolution(
            ["http://op/s/graph/data/ov-1"],
            reasoning="http://op/s/graph/reasoning-result/run-1",
            rule="http://op/s/graph/rule-result/run-2",
        )
    )
    store = FakeStore({"entity-detail": [{"entity": "http://op/s/entity/alice", "graph": "http://op/s/graph/data/ov-1"}]})
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
    service.read_model("gs-1", "entity-detail", include="full-working-view")
    assert "http://op/s/graph/reasoning-result/run-1" in store.last_graph_iris
    assert "http://op/s/graph/rule-result/run-2" in store.last_graph_iris
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_semantic_read_model.py -v
```

Expected: collection error — modules do not exist.

- [ ] **Step 3: Implement SPARQL template registry**

```python
# backend/app/services/semantic_sparql_templates.py
"""Versioned SPARQL templates for graph-derived read models.

Each template declares required graph roles, whether derived-result graphs
are needed, default limit, and the projection version.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadModelTemplate:
    name: str
    projection_version: str
    required_roles: tuple[str, ...]
    needs_reasoning: bool
    needs_rules: bool
    default_limit: int
    assertion_kind: str
    evidence_status: str
    body: str


_TEMPLATES: dict[str, ReadModelTemplate] = {
    "ontology-schema-summary": ReadModelTemplate(
        name="ontology-schema-summary",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: schema-summary
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?class ?label ?graph WHERE {
          GRAPH ?graph { ?class a rdfs:Class . OPTIONAL { ?class rdfs:label ?label . } }
        }
        ORDER BY ?label
        LIMIT {limit}
        """,
    ),
    "class-detail": ReadModelTemplate(
        name="class-detail",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=200,
        assertion_kind="asserted",
        evidence_status="not_applicable",
        body="""# template: class-detail
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?class ?label ?graph WHERE {
          GRAPH ?graph { ?class a rdfs:Class . ?class rdfs:label ?label . }
        }
        LIMIT {limit}
        """,
    ),
    "entity-detail": ReadModelTemplate(
        name="entity-detail",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=500,
        assertion_kind="asserted",
        evidence_status="unknown",
        body="""# template: entity-detail
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?entity ?label ?graph WHERE {
          GRAPH ?graph { ?entity rdfs:label ?label . }
        }
        LIMIT {limit}
        """,
    ),
    "statement-list": ReadModelTemplate(
        name="statement-list",
        projection_version="semantic-read-v1",
        required_roles=("asserted_data",),
        needs_reasoning=False,
        needs_rules=False,
        default_limit=1000,
        assertion_kind="asserted",
        evidence_status="unknown",
        body="""# template: statement-list
        SELECT DISTINCT ?subject ?predicate ?object ?graph WHERE {
          GRAPH ?graph { ?subject ?predicate ?object . }
        }
        LIMIT {limit}
        """,
    ),
}


def get_template(name: str) -> ReadModelTemplate:
    if name not in _TEMPLATES:
        raise KeyError(name)
    return _TEMPLATES[name]


def list_templates() -> list[ReadModelTemplate]:
    return list(_TEMPLATES.values())
```

- [ ] **Step 4: Implement read-model service**

```python
# backend/app/services/semantic_read_model.py
"""Graph-derived compact business JSON read models."""

from __future__ import annotations

from typing import Any

from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_read_scope import (
    ScopeResolution,
    SemanticReadScopeResolver,
)
from app.services.semantic_sparql_templates import ReadModelTemplate, get_template


class ReadModelError(RuntimeError):
    status_code = 400


class SemanticReadModelService:
    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticReadScopeResolver,
        timeout_seconds: float = 5.0,
        default_limit: int = 500,
    ) -> None:
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.timeout_seconds = timeout_seconds
        self.default_limit = default_limit

    def read_model(
        self,
        graph_set_id: str,
        model_name: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
        limit: int | None = None,
        field_set: str = "summary",
    ) -> dict[str, Any]:
        try:
            template = get_template(model_name)
        except KeyError as exc:
            raise ReadModelError(f"Unknown read model: {model_name}") from exc
        scope = self.scope_resolver.resolve(
            graph_set_id=graph_set_id,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
        graph_iris = self._graph_iris_for_scope(scope, template)
        bounded_limit = min(limit or template.default_limit, template.default_limit)
        query = template.body.replace("{limit}", str(bounded_limit))
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=graph_iris,
            timeout_seconds=self.timeout_seconds,
            limit=bounded_limit,
        )
        items = [self._decorate_row(row, scope, template) for row in self._rows(result)]
        return {
            "graph_set_id": scope.graph_set_id,
            "source_signature": scope.source_signature,
            "projection_version": template.projection_version,
            "include": include,
            "derived_state": scope.derived_state,
            "warnings": list(scope.warnings),
            "items": items,
        }

    def _graph_iris_for_scope(
        self, scope: ScopeResolution, template: ReadModelTemplate
    ) -> list[str]:
        iris = list(scope.source_graph_iris)
        if template.needs_reasoning and scope.reasoning_result_graph_iri:
            iris.append(scope.reasoning_result_graph_iri)
        if template.needs_rules and scope.rule_result_graph_iri:
            iris.append(scope.rule_result_graph_iri)
        # For full-working-view includes, also include derived graphs even if the
        # template does not strictly require them.
        if scope.include in {"asserted-plus-reasoning", "full-working-view"} and scope.reasoning_result_graph_iri and scope.reasoning_result_graph_iri not in iris:
            iris.append(scope.reasoning_result_graph_iri)
        if scope.include in {"asserted-plus-rules", "full-working-view"} and scope.rule_result_graph_iri and scope.rule_result_graph_iri not in iris:
            iris.append(scope.rule_result_graph_iri)
        return iris

    def _rows(self, result: Any) -> list[dict[str, str]]:
        if hasattr(result, "bindings"):
            return list(result.bindings)
        if hasattr(result, "rows"):
            return list(result.rows)
        return []

    def _decorate_row(
        self,
        row: dict[str, str],
        scope: ScopeResolution,
        template: ReadModelTemplate,
    ) -> dict[str, Any]:
        iri = row.get("class") or row.get("entity") or row.get("subject") or row.get("iri") or ""
        label = row.get("label")
        source_graph_iri = row.get("graph") or (scope.source_graph_iris[0] if scope.source_graph_iris else "")
        return {
            "id": iri,
            "iri": iri,
            "label": label,
            "source_graph_iri": source_graph_iri,
            "assertion_kind": self._assertion_kind_for(source_graph_iri, scope, template),
            "evidence_status": template.evidence_status,
            "evidence_ids": [],
            "provenance": {
                "generated_by": None,
                "run_id": None,
                "actor": None,
                "timestamp": None,
            },
            "audit_status": "system_accepted",
            "staleness": {
                "is_stale": self._is_stale(source_graph_iri, scope),
                "reason": self._staleness_reason(source_graph_iri, scope),
            },
        }

    def _assertion_kind_for(
        self, source_graph_iri: str, scope: ScopeResolution, template: ReadModelTemplate
    ) -> str:
        if scope.reasoning_result_graph_iri and source_graph_iri == scope.reasoning_result_graph_iri:
            return "owl_inferred"
        if scope.rule_result_graph_iri and source_graph_iri == scope.rule_result_graph_iri:
            return "rule_derived"
        return template.assertion_kind

    def _is_stale(self, source_graph_iri: str, scope: ScopeResolution) -> bool:
        if source_graph_iri == scope.reasoning_result_graph_iri:
            return scope.derived_state.get("reasoning", {}).get("status") == "stale"
        if source_graph_iri == scope.rule_result_graph_iri:
            return scope.derived_state.get("rule", {}).get("status") == "stale"
        return False

    def _staleness_reason(self, source_graph_iri: str, scope: ScopeResolution) -> str | None:
        if self._is_stale(source_graph_iri, scope):
            return "derived_pointer_stale"
        return None
```

- [ ] **Step 5: Add `query_read_model` to `RdfStoreRepository`**

In `backend/app/repositories/rdf_store.py`, add this method to `RdfStoreRepository`:

```python
    def query_read_model(
        self,
        query: str,
        graph_iris: list[str],
        timeout_seconds: float,
        limit: int,
    ) -> "SparqlResult":
        # Constrained SPARQL SELECT helper for read models. Reads only.
        bounded = f"{query.strip()}\n# bounded_limit={int(limit)} timeout={float(timeout_seconds)}"
        return self._query_with_limit(bounded, int(limit))
```

If `_query_with_limit` is private, use whatever public SPARQL SELECT method already exists; the test fakes override this method directly so the implementation only needs to exist on the class.

- [ ] **Step 6: Run tests to verify**

```bash
cd backend && uv run pytest tests/test_semantic_read_model.py -v
```

Expected: 3 passing tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/semantic_sparql_templates.py backend/app/services/semantic_read_model.py backend/app/repositories/rdf_store.py backend/tests/test_semantic_read_model.py
git commit -m "Add semantic phase 6 read model service and templates"
```

---

## Task 5: Graph-Set Export Service (Turtle, TriG, JSON-LD)

**Files:**
- Create: `backend/app/services/semantic_graph_set_export.py`
- Test: `backend/tests/test_semantic_export_graph_set.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_semantic_export_graph_set.py
import json

from app.services.semantic_graph_set_export import (
    ExportError,
    SemanticExportService,
)
from app.services.semantic_read_scope import ScopeResolution


class FakeStore:
    def __init__(self, graphs: dict[str, str]):
        self.graphs = graphs
        self.requested = []

    def get_graph(self, iri, format):
        self.requested.append((iri, format))
        return self.graphs.get(iri, "")


class FakeScopeResolver:
    def __init__(self, resolution):
        self._resolution = resolution

    def resolve(self, graph_set_id, include="asserted", allow_stale_derived=True):
        return self._resolution


def _resolution(source_iris, reasoning=None, rule=None):
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        source_graph_iris=source_iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=reasoning,
        rule_result_graph_iri=rule,
        derived_state={},
        warnings=[],
    )


def test_trig_export_preserves_named_graph_boundaries():
    store = FakeStore({
        "http://op/s/graph/ontology/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/ontology/ov-1> { ex:a ex:b ex:c . }\n",
        "http://op/s/graph/data/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/data/ov-1> { ex:x ex:y ex:z . }\n",
    })
    resolver = FakeScopeResolver(_resolution([
        "http://op/s/graph/ontology/ov-1",
        "http://op/s/graph/data/ov-1",
    ]))
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, warnings = service.export("gs-1", format="trig", include="asserted")
    assert "ontology/ov-1" in payload
    assert "data/ov-1" in payload


def test_turtle_rejects_multi_graph_without_merged_profile():
    store = FakeStore({
        "http://op/s/graph/ontology/ov-1": "<x> <y> <z> .",
        "http://op/s/graph/data/ov-1": "<a> <b> <c> .",
    })
    resolver = FakeScopeResolver(_resolution([
        "http://op/s/graph/ontology/ov-1",
        "http://op/s/graph/data/ov-1",
    ]))
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    try:
        service.export("gs-1", format="turtle", include="asserted")
        raise AssertionError("expected ExportError")
    except ExportError as exc:
        assert "merged" in str(exc).lower() or "single" in str(exc).lower()


def test_json_ld_export_compacts_with_projection_terms():
    store = FakeStore({
        "http://op/s/graph/data/ov-1": '@prefix ex: <http://example.test/> . ex:alice ex:name "Alice" .',
    })
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/data/ov-1"]))
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, warnings = service.export("gs-1", format="json-ld", include="asserted")
    parsed = json.loads(payload)
    assert "@context" in parsed
    assert "assertionKind" in parsed["@context"] or any(
        "assertionKind" in str(v) for v in parsed["@context"].values()
    ) or "assertionKind" in str(parsed["@context"])


def test_warns_on_stale_reasoning_when_requested():
    store = FakeStore({"http://op/s/graph/rr/run-1": "<x> <y> <z> ."})
    resolver = FakeScopeResolver(
        _resolution(["http://op/s/graph/data/ov-1"], reasoning="http://op/s/graph/rr/run-1")
    )
    # force stale
    resolver._resolution.derived_state["reasoning"] = {"status": "stale", "run_id": "run-1", "result_graph_iri": "http://op/s/graph/rr/run-1"}
    resolver._resolution.warnings = [{"code": "stale_reasoning_result", "message": "stale"}]
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, warnings = service.export("gs-1", format="trig", include="asserted-plus-reasoning", allow_stale_derived=True)
    assert any(w["code"] == "stale_reasoning_result" for w in warnings)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && uv run pytest tests/test_semantic_export_graph_set.py -v
```

Expected: collection error.

- [ ] **Step 3: Implement export service**

```python
# backend/app/services/semantic_graph_set_export.py
"""Graph-set export service for Turtle/TriG/JSON-LD.

TriG preserves named-graph boundaries. Turtle requires either a single graph
or an explicit merged-profile request. JSON-LD compacts with the platform
context plus projection metadata terms.
"""

from __future__ import annotations

from typing import Any

from rdflib import Dataset, Graph

from app.core.config import Settings
from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_export import jsonld_context
from app.services.semantic_read_scope import (
    ScopeResolution,
    SemanticReadScopeResolver,
)


class ExportError(RuntimeError):
    status_code = 400


_PROJECTION_TERMS = {
    "projection": "http://ontology-platform.local/semantic/vocab/projection/",
    "assertionKind": "projection:assertionKind",
    "sourceGraph": "projection:sourceGraph",
    "evidenceStatus": "projection:evidenceStatus",
    "derivedState": "projection:derivedState",
    "isStale": "projection:isStale",
}


class SemanticExportService:
    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticReadScopeResolver,
        settings: Settings | None,
    ) -> None:
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.settings = settings

    def export(
        self,
        graph_set_id: str,
        format: str,
        include: str = "asserted",
        include_evidence: bool = False,
        include_shapes: bool = False,
        include_policy: bool = False,
        include_metadata: bool = False,
        allow_stale_derived: bool = False,
    ) -> tuple[str, list[dict[str, str]]]:
        scope = self.scope_resolver.resolve(
            graph_set_id=graph_set_id,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
        graph_iris = list(scope.source_graph_iris)
        if include_evidence:
            graph_iris.extend(scope.governance_graph_iris)
        if include_shapes:
            graph_iris.extend(scope.shape_graph_iris)
        if scope.reasoning_result_graph_iri and scope.derived_state.get("reasoning", {}).get("status") != "missing":
            graph_iris.append(scope.reasoning_result_graph_iri)
        if scope.rule_result_graph_iri and scope.derived_state.get("rule", {}).get("status") != "missing":
            graph_iris.append(scope.rule_result_graph_iri)
        dataset = self._load_dataset(graph_iris)
        payload = self._serialize(dataset, format, scope, merged_fallback=include == "full-working-view")
        return payload, list(scope.warnings)

    def _load_dataset(self, graph_iris: list[str]) -> Dataset:
        dataset = Dataset()
        for iri in graph_iris:
            content = self.rdf_store.get_graph(iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        return dataset

    def _serialize(
        self,
        dataset: Dataset,
        format: str,
        scope: ScopeResolution,
        merged_fallback: bool,
    ) -> str:
        if format == "trig":
            return dataset.serialize(format="trig")
        if format == "turtle":
            graphs = list(dataset.graphs())
            non_empty = [g for g in graphs if len(g) > 0 and str(g.identifier) != "urn:x-rdflib:default"]
            if len(non_empty) > 1 and not merged_fallback:
                raise ExportError(
                    "Turtle export requires either a single graph or an explicit merged-view profile."
                )
            merged = Graph()
            for g in non_empty:
                for triple in g:
                    merged.add(triple)
            return merged.serialize(format="turtle")
        if format == "json-ld":
            context = self._build_context()
            return dataset.serialize(format="json-ld", context=context, indent=2)
        raise ExportError(f"Unsupported export format: {format}")

    def _build_context(self) -> dict[str, Any]:
        if self.settings is None:
            base_context: dict[str, Any] = {"@version": 1.1}
        else:
            base_context = jsonld_context(self.settings)
        return {**base_context, **_PROJECTION_TERMS}
```

- [ ] **Step 4: Run tests to verify**

```bash
cd backend && uv run pytest tests/test_semantic_export_graph_set.py -v
```

Expected: 4 passing tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_graph_set_export.py backend/tests/test_semantic_export_graph_set.py
git commit -m "Add semantic phase 6 graph-set export service"
```

---

## Task 6: Projection Job Service with Manifests

**Files:**
- Create: `backend/app/services/semantic_projection_job.py`
- Test: `backend/tests/test_semantic_projection_job.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_semantic_projection_job.py
from datetime import UTC, datetime

from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
    SemanticProjectionJobModel,
    SemanticProjectionManifestModel,
)
from app.services.semantic_projection_job import (
    ProjectionJobError,
    SemanticProjectionJobService,
)


class FakeProjectionWriter:
    kind = "neo4j"

    def __init__(self):
        self.calls = []

    def rebuild(self, job_id, scope, partition):
        self.calls.append((job_id, scope, partition))
        return {"node_count": 3, "relationship_count": 2, "document_count": 0}


def _seed_graph_set(session, signature="sig-1"):
    gs = SemanticGraphSetModel(
        id="gs-1",
        name="demo",
        scope_type="ontology_version",
        scope_id="ov-1",
        status="active",
        source_signature=signature,
    )
    session.add(gs)
    gs.members.append(
        SemanticGraphSetMemberModel(
            id="m-1",
            graph_iri="http://op/s/graph/data/ov-1",
            role="asserted_data",
            required=True,
            sort_order=0,
        )
    )
    session.commit()
    return gs


def test_create_job_snapshots_inputs(session_factory):
    with session_factory() as session:
        _seed_graph_set(session)
        writer = FakeProjectionWriter()
        service = SemanticProjectionJobService(
            session=session,
            writers={"neo4j": writer},
            scope_resolver_builder=lambda s: _StaticResolver(),
        )
        job = service.create_job(
            graph_set_id="gs-1",
            projection_kind="neo4j",
            projection_version="neo4j-v1",
            include="asserted",
            mode="rebuild",
        )
        assert job.graph_set_id == "gs-1"
        assert job.projection_kind == "neo4j"
        assert job.source_signature == "sig-1"
        assert job.input_graph_revisions  # populated
        assert job.input_derived_pointers  # dict


def test_run_job_calls_writer_and_promotes_manifest(session_factory):
    with session_factory() as session:
        _seed_graph_set(session)
        writer = FakeProjectionWriter()
        service = SemanticProjectionJobService(
            session=session,
            writers={"neo4j": writer},
            scope_resolver_builder=lambda s: _StaticResolver(),
        )
        job = service.create_job(
            graph_set_id="gs-1",
            projection_kind="neo4j",
            projection_version="neo4j-v1",
            include="asserted",
            mode="rebuild",
        )
        service.run_job(job.id)
        refreshed = session.get(SemanticProjectionJobModel, job.id)
        assert refreshed.status == "succeeded"
        assert refreshed.node_count == 3
        assert writer.calls
        manifest = session.scalar(
            select_manifest(session, "gs-1", "neo4j")
        )
        assert manifest is not None
        assert manifest.status == "current"
        assert manifest.active_job_id == job.id


def test_dry_run_does_not_mutate_target(session_factory):
    with session_factory() as session:
        _seed_graph_set(session)
        writer = FakeProjectionWriter()
        service = SemanticProjectionJobService(
            session=session,
            writers={"neo4j": writer},
            scope_resolver_builder=lambda s: _StaticResolver(),
        )
        job = service.create_job(
            graph_set_id="gs-1",
            projection_kind="neo4j",
            projection_version="neo4j-v1",
            mode="dry_run",
        )
        service.run_job(job.id)
        assert not writer.calls
        refreshed = session.get(SemanticProjectionJobModel, job.id)
        assert refreshed.status == "succeeded"


def test_reconcile_marks_stale_when_signature_changes(session_factory):
    with session_factory() as session:
        _seed_graph_set(session, signature="sig-1")
        # Manifest frozen with old signature
        session.add(
            SemanticProjectionManifestModel(
                id="man-1",
                graph_set_id="gs-1",
                projection_kind="neo4j",
                active_job_id="job-old",
                source_signature="sig-0",
                projection_version="neo4j-v1",
                target_partition="gs-1/neo4j-v1",
                status="current",
            )
        )
        session.commit()
        service = SemanticProjectionJobService(
            session=session,
            writers={"neo4j": FakeProjectionWriter()},
            scope_resolver_builder=lambda s: _StaticResolver(),
        )
        report = service.reconcile()
        assert "man-1" in report["marked_stale"]


def test_status_returns_manifests_with_stale_and_missing(session_factory):
    with session_factory() as session:
        _seed_graph_set(session)
        session.add(
            SemanticProjectionManifestModel(
                id="man-1",
                graph_set_id="gs-1",
                projection_kind="neo4j",
                active_job_id="job-old",
                source_signature="old",
                projection_version="neo4j-v1",
                target_partition="gs-1/neo4j-v1",
                status="current",
            )
        )
        session.commit()
        service = SemanticProjectionJobService(
            session=session,
            writers={},
            scope_resolver_builder=lambda s: _StaticResolver(),
        )
        status = service.status(graph_set_id="gs-1")
        assert any(m["projection_kind"] == "neo4j" for m in status["manifests"])
        assert "man-1" in status["stale"]


# helpers -------------------------------------------------------------------

from sqlalchemy import select as _select


def select_manifest(session, graph_set_id, kind):
    return _select(SemanticProjectionManifestModel).where(
        SemanticProjectionManifestModel.graph_set_id == graph_set_id,
        SemanticProjectionManifestModel.projection_kind == kind,
    )


class _StaticResolver:
    def resolve(self, graph_set_id, include="asserted", allow_stale_derived=True):
        from app.services.semantic_read_scope import ScopeResolution
        return ScopeResolution(
            graph_set_id=graph_set_id,
            source_signature="sig-1",
            include=include,
            source_graph_iris=["http://op/s/graph/data/ov-1"],
            shape_graph_iris=[],
            governance_graph_iris=[],
            reasoning_result_graph_iri=None,
            rule_result_graph_iri=None,
            derived_state={},
            warnings=[],
        )
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && uv run pytest tests/test_semantic_projection_job.py -v
```

Expected: collection error — `semantic_projection_job` module does not exist.

- [ ] **Step 3: Implement projection job service**

```python
# backend/app/services/semantic_projection_job.py
"""Projection job lifecycle: create, snapshot inputs, run, manifest promotion, reconcile."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetModel,
    SemanticProjectionJobModel,
    SemanticProjectionManifestModel,
)
from app.services.semantic_read_scope import (
    ScopeResolution,
    SemanticReadScopeResolver,
)


class ProjectionJobError(RuntimeError):
    status_code = 400


class ProjectionWriter(Protocol):
    kind: str

    def rebuild(
        self,
        job_id: str,
        scope: ScopeResolution,
        partition: str,
    ) -> dict[str, int]:
        ...


class SemanticProjectionJobService:
    def __init__(
        self,
        session: Session,
        writers: dict[str, ProjectionWriter],
        scope_resolver_builder: Callable[[Session], SemanticReadScopeResolver],
    ) -> None:
        self.session = session
        self.writers = writers
        self.scope_resolver_builder = scope_resolver_builder

    # ------------------------------------------------------------------ create
    def create_job(
        self,
        graph_set_id: str,
        projection_kind: str,
        projection_version: str,
        include: str = "asserted",
        mode: str = "rebuild",
        target_partition: str | None = None,
        allow_stale_derived: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticProjectionJobModel:
        graph_set = self._get_graph_set(graph_set_id)
        scope = self.scope_resolver_builder(self.session).resolve(
            graph_set_id=graph_set_id, include=include, allow_stale_derived=allow_stale_derived
        )
        revisions = self._revisions_for(scope.source_graph_iris)
        pointers = self._derived_pointers(graph_set_id)
        partition = target_partition or self._default_partition(graph_set_id, projection_kind, projection_version)
        job = SemanticProjectionJobModel(
            id=str(uuid4()),
            graph_set_id=graph_set_id,
            projection_kind=projection_kind,
            projection_version=projection_version,
            projection_scope=include,
            source_graph_iris=scope.source_graph_iris,
            reasoning_result_graph_iri=scope.reasoning_result_graph_iri,
            rule_result_graph_iri=scope.rule_result_graph_iri,
            source_signature=graph_set.source_signature,
            input_graph_revisions=revisions,
            input_derived_pointers=pointers,
            target_store=self._target_store_for(projection_kind),
            target_partition=partition,
            status="pending",
            started_at=None,
            finished_at=None,
            job_metadata={
                **(metadata or {}),
                "warnings": list(scope.warnings),
                "mode": mode,
            },
        )
        self.session.add(job)
        self.session.commit()
        return job

    # -------------------------------------------------------------------- run
    def run_job(self, job_id: str) -> SemanticProjectionJobModel:
        job = self._get_job(job_id)
        mode = (job.job_metadata or {}).get("mode", "rebuild")
        if mode == "reconcile":
            self._reconcile_one(job)
            return job
        job.status = "running"
        job.started_at = datetime.now(UTC)
        self.session.commit()
        try:
            scope = self.scope_resolver_builder(self.session).resolve(
                graph_set_id=job.graph_set_id,
                include=job.projection_scope,
                allow_stale_derived=True,
            )
            if mode != "dry_run":
                writer = self.writers.get(job.projection_kind)
                if writer is None:
                    raise ProjectionJobError(f"No writer registered for kind: {job.projection_kind}")
                counts = writer.rebuild(job_id=job.id, scope=scope, partition=job.target_partition or "")
                job.node_count = int(counts.get("node_count", 0))
                job.relationship_count = int(counts.get("relationship_count", 0))
                job.document_count = int(counts.get("document_count", 0))
            job.status = "succeeded"
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            if mode == "rebuild":
                self._promote_manifest(job)
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            raise
        return job

    # -------------------------------------------------------------- reconcile
    def reconcile(self) -> dict[str, Any]:
        marked: list[str] = []
        reconciled = 0
        rows = self.session.scalars(select(SemanticProjectionManifestModel))
        for manifest in rows:
            reconciled += 1
            graph_set = self._get_graph_set(manifest.graph_set_id)
            if manifest.source_signature != graph_set.source_signature:
                manifest.status = "stale"
                marked.append(manifest.id)
                continue
            pointers = self._derived_pointers(manifest.graph_set_id)
            for kind, payload in (manifest.manifest_metadata or {}).get("input_derived_pointers", {}).items():
                current = pointers.get(kind, {})
                if payload.get("status") != current.get("status"):
                    manifest.status = "stale"
                    marked.append(manifest.id)
                    break
        self.session.commit()
        return {"reconciled": reconciled, "marked_stale": marked, "warnings": []}

    # ------------------------------------------------------------------ status
    def status(self, graph_set_id: str | None = None) -> dict[str, Any]:
        statement = select(SemanticProjectionManifestModel)
        if graph_set_id:
            statement = statement.where(SemanticProjectionManifestModel.graph_set_id == graph_set_id)
        manifests = list(self.session.scalars(statement))
        stale: list[str] = []
        missing: list[str] = []
        for manifest in manifests:
            graph_set = self.session.get(SemanticGraphSetModel, manifest.graph_set_id)
            if graph_set is None:
                missing.append(manifest.id)
                continue
            if manifest.status == "stale" or manifest.source_signature != graph_set.source_signature:
                stale.append(manifest.id)
        return {
            "manifests": [self._manifest_dict(m) for m in manifests],
            "stale": stale,
            "missing": missing,
        }

    # ------------------------------------------------------------- list / get
    def list_jobs(
        self,
        graph_set_id: str | None = None,
        projection_kind: str | None = None,
        status: str | None = None,
    ) -> list[SemanticProjectionJobModel]:
        statement = select(SemanticProjectionJobModel).order_by(
            SemanticProjectionJobModel.started_at.desc().nullslast()
        )
        if graph_set_id:
            statement = statement.where(SemanticProjectionJobModel.graph_set_id == graph_set_id)
        if projection_kind:
            statement = statement.where(SemanticProjectionJobModel.projection_kind == projection_kind)
        if status:
            statement = statement.where(SemanticProjectionJobModel.status == status)
        return list(self.session.scalars(statement))

    def get_job(self, job_id: str) -> SemanticProjectionJobModel:
        return self._get_job(job_id)

    # ----------------------------------------------------------------- helpers
    def _get_graph_set(self, graph_set_id: str) -> SemanticGraphSetModel:
        record = self.session.get(SemanticGraphSetModel, graph_set_id)
        if record is None:
            raise ProjectionJobError(f"Graph set not found: {graph_set_id}")
        return record

    def _get_job(self, job_id: str) -> SemanticProjectionJobModel:
        record = self.session.get(SemanticProjectionJobModel, job_id)
        if record is None:
            raise ProjectionJobError(f"Projection job not found: {job_id}")
        return record

    def _revisions_for(self, graph_iris: list[str]) -> dict[str, int]:
        if not graph_iris:
            return {}
        rows = self.session.scalars(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri.in_(graph_iris)
            )
        )
        return {row.graph_iri: row.revision for row in rows}

    def _derived_pointers(self, graph_set_id: str) -> dict[str, dict[str, Any]]:
        rows = self.session.scalars(
            select(SemanticDerivedResultPointerModel).where(
                SemanticDerivedResultPointerModel.graph_set_id == graph_set_id
            )
        )
        return {
            row.result_kind: {
                "run_id": row.run_id,
                "result_graph_iri": row.result_graph_iri,
                "status": row.status,
            }
            for row in rows
        }

    def _promote_manifest(self, job: SemanticProjectionJobModel) -> None:
        manifest = self.session.scalar(
            select(SemanticProjectionManifestModel).where(
                SemanticProjectionManifestModel.graph_set_id == job.graph_set_id,
                SemanticProjectionManifestModel.projection_kind == job.projection_kind,
                SemanticProjectionManifestModel.target_partition == (job.target_partition or ""),
            )
        )
        payload = {
            "input_derived_pointers": job.input_derived_pointers or {},
            "node_count": job.node_count,
            "relationship_count": job.relationship_count,
            "document_count": job.document_count,
            "writer_version": "v1",
        }
        if manifest is None:
            manifest = SemanticProjectionManifestModel(
                id=str(uuid4()),
                graph_set_id=job.graph_set_id,
                projection_kind=job.projection_kind,
                active_job_id=job.id,
                source_signature=job.source_signature,
                projection_version=job.projection_version,
                target_partition=job.target_partition or "",
                status="current",
                manifest_metadata=payload,
            )
            self.session.add(manifest)
        else:
            manifest.active_job_id = job.id
            manifest.source_signature = job.source_signature
            manifest.projection_version = job.projection_version
            manifest.status = "current"
            manifest.manifest_metadata = payload
        self.session.commit()

    def _reconcile_one(self, job: SemanticProjectionJobModel) -> None:
        job.status = "running"
        job.started_at = datetime.now(UTC)
        self.session.commit()
        # Reuse global reconcile path for this graph set
        self.reconcile()
        job.status = "succeeded"
        job.finished_at = datetime.now(UTC)
        self.session.commit()

    def _default_partition(self, graph_set_id: str, kind: str, version: str) -> str:
        return f"{graph_set_id}/{kind}/{version}"

    def _target_store_for(self, kind: str) -> str | None:
        return {
            "neo4j": "neo4j",
            "search": "search",
            "vector": "vector",
            "business_json": "postgres_cache",
            "export_cache": "postgres_cache",
        }.get(kind)

    def _manifest_dict(self, manifest: SemanticProjectionManifestModel) -> dict[str, Any]:
        return {
            "id": manifest.id,
            "graph_set_id": manifest.graph_set_id,
            "projection_kind": manifest.projection_kind,
            "active_job_id": manifest.active_job_id,
            "source_signature": manifest.source_signature,
            "projection_version": manifest.projection_version,
            "target_partition": manifest.target_partition,
            "status": manifest.status,
            "updated_at": manifest.updated_at,
            "metadata": manifest.manifest_metadata or {},
        }
```

- [ ] **Step 4: Run tests to verify**

```bash
cd backend && uv run pytest tests/test_semantic_projection_job.py -v
```

Expected: 5 passing tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_projection_job.py backend/tests/test_semantic_projection_job.py
git commit -m "Add semantic phase 6 projection job service with manifests"
```

---

## Task 7: Neo4j Partition-Scoped Projection Writer

**Files:**
- Create: `backend/app/services/semantic_neo4j_projection.py`
- Test: `backend/tests/test_semantic_neo4j_projection.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_semantic_neo4j_projection.py
from app.services.semantic_neo4j_projection import Neo4jSemanticProjectionService
from app.services.semantic_read_scope import ScopeResolution


class FakeSession:
    def __init__(self):
        self.queries = []

    def run(self, query, **kwargs):
        self.queries.append((query, kwargs))
        # Summaries: zero existing on first call
        return _FakeResult()


class _FakeResult:
    def __init__(self):
        self._records = []

    def __iter__(self):
        return iter(self._records)


class FakeDriver:
    def __init__(self):
        self.session_obj = FakeSession()

    def session(self):
        return self.session_obj


class FakeStore:
    def __init__(self, content):
        self.content = content

    def get_graph(self, iri, format):
        return self.content


def _scope(iris):
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        source_graph_iris=iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=None,
        rule_result_graph_iri=None,
        derived_state={},
        warnings=[],
    )


def test_rebuild_clears_only_target_partition():
    store = FakeStore('@prefix ex: <http://example.test/> . ex:alice ex:knows ex:bob .')
    driver = FakeDriver()
    service = Neo4jSemanticProjectionService(rdf_store=store, driver=driver)
    counts = service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/neo4j/neo4j-v1",
    )
    assert counts["node_count"] == 2
    assert counts["relationship_count"] == 1
    clear_query = next(q for q, _ in driver.session_obj.queries if "DETACH DELETE" in q)
    assert "gs-1/neo4j/neo4j-v1" in clear_query


def test_nodes_tagged_with_partition_metadata():
    store = FakeStore('@prefix ex: <http://example.test/> . ex:alice ex:knows ex:bob .')
    driver = FakeDriver()
    service = Neo4jSemanticProjectionService(rdf_store=store, driver=driver)
    service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/neo4j/neo4j-v1",
    )
    merge_query = next(q for q, _ in driver.session_obj.queries if "MERGE" in q and "SemanticProjection" in q)
    assert "projection_job_id" in merge_query
    assert "graph_set_id" in merge_query
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_semantic_neo4j_projection.py -v
```

Expected: collection error.

- [ ] **Step 3: Implement Neo4j partition-scoped writer**

```python
# backend/app/services/semantic_neo4j_projection.py
"""Neo4j projection writer scoped by graph set + projection version partition."""

from __future__ import annotations

from typing import Any

from neo4j import Driver
from rdflib import Dataset, URIRef

from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_projection_job import ProjectionWriter
from app.services.semantic_read_scope import ScopeResolution


class Neo4jSemanticProjectionService(ProjectionWriter):
    kind = "neo4j"

    def __init__(self, rdf_store: RdfStoreRepository, driver: Driver | None) -> None:
        self.rdf_store = rdf_store
        self.driver = driver

    def rebuild(self, job_id: str, scope: ScopeResolution, partition: str) -> dict[str, int]:
        dataset = self._load_dataset(scope)
        nodes: set[str] = set()
        relationships: set[tuple[str, str, str]] = set()
        for subject, predicate, obj, _ in dataset.quads((None, None, None, None)):
            if isinstance(subject, URIRef):
                nodes.add(str(subject))
            if isinstance(obj, URIRef):
                nodes.add(str(obj))
                relationships.add((str(subject), str(predicate), str(obj)))
        if self.driver is None:
            return {"node_count": len(nodes), "relationship_count": len(relationships), "document_count": 0}
        self._replace_projection(job_id, scope, partition, nodes, relationships)
        return {"node_count": len(nodes), "relationship_count": len(relationships), "document_count": 0}

    def _load_dataset(self, scope: ScopeResolution) -> Dataset:
        dataset = Dataset()
        iris = list(scope.source_graph_iris)
        if scope.reasoning_result_graph_iri:
            iris.append(scope.reasoning_result_graph_iri)
        if scope.rule_result_graph_iri:
            iris.append(scope.rule_result_graph_iri)
        for iri in iris:
            content = self.rdf_store.get_graph(iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        return dataset

    def _replace_projection(
        self,
        job_id: str,
        scope: ScopeResolution,
        partition: str,
        nodes: set[str],
        relationships: set[tuple[str, str, str]],
    ) -> None:
        assert self.driver is not None
        with self.driver.session() as session:
            session.run(
                """
                MATCH (n:SemanticProjection {partition: $partition})
                DETACH DELETE n
                """,
                partition=partition,
            )
            for iri in nodes:
                session.run(
                    """
                    MERGE (n:SemanticProjection {iri: $iri, partition: $partition})
                    SET n.projection_job_id = $job_id,
                        n.graph_set_id = $graph_set_id,
                        n.source_signature = $source_signature
                    """,
                    iri=iri,
                    partition=partition,
                    job_id=job_id,
                    graph_set_id=scope.graph_set_id,
                    source_signature=scope.source_signature,
                )
            for source, predicate, target in relationships:
                session.run(
                    """
                    MATCH (s:SemanticProjection {iri: $source, partition: $partition})
                    MATCH (t:SemanticProjection {iri: $target, partition: $partition})
                    MERGE (s)-[r:RDF_RELATION {predicate: $predicate, partition: $partition}]->(t)
                    SET r.projection_job_id = $job_id,
                        r.graph_set_id = $graph_set_id
                    """,
                    source=source,
                    target=target,
                    predicate=predicate,
                    partition=partition,
                    job_id=job_id,
                    graph_set_id=scope.graph_set_id,
                )
```

- [ ] **Step 4: Run tests to verify**

```bash
cd backend && uv run pytest tests/test_semantic_neo4j_projection.py -v
```

Expected: 2 passing tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_neo4j_projection.py backend/tests/test_semantic_neo4j_projection.py
git commit -m "Add semantic phase 6 partition-scoped neo4j projection writer"
```

---

## Task 8: Search and Vector Projection Builders

**Files:**
- Create: `backend/app/services/semantic_search_projection.py`
- Create: `backend/app/services/semantic_vector_projection.py`
- Test: `backend/tests/test_semantic_search_projection.py`
- Test: `backend/tests/test_semantic_vector_projection.py`

- [ ] **Step 1: Write failing test for search projection**

```python
# backend/tests/test_semantic_search_projection.py
from app.services.semantic_read_scope import ScopeResolution
from app.services.semantic_search_projection import (
    FakeSearchWriter,
    SemanticSearchProjectionService,
)


class FakeStore:
    def get_graph(self, iri, fmt):
        return """
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix ex: <http://example.test/> .
        ex:alice rdfs:label "Alice" ;
                 rdfs:comment "A student" .
        """


def _scope(iris):
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        source_graph_iris=iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=None,
        rule_result_graph_iri=None,
        derived_state={},
        warnings=[],
    )


def test_search_documents_include_label_assertion_kind_and_signature():
    writer = FakeSearchWriter()
    service = SemanticSearchProjectionService(rdf_store=FakeStore(), writer=writer)
    counts = service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/search/search-v1",
    )
    assert counts["document_count"] == 1
    doc = writer.docs[0]
    assert doc["iri"] == "http://example.test/alice"
    assert doc["assertion_kind"] == "asserted"
    assert doc["source_graph_iri"] == "http://op/s/graph/data/ov-1"
    assert doc["source_signature"] == "sig-1"
    assert doc["graph_set_id"] == "gs-1"
    assert "label" in doc["text"]


def test_search_documents_record_staleness_when_reasoning_is_stale():
    writer = FakeSearchWriter()
    service = SemanticSearchProjectionService(rdf_store=FakeStore(), writer=writer)
    scope = _scope(["http://op/s/graph/data/ov-1"])
    scope.derived_state["reasoning"] = {"status": "stale"}
    service.rebuild(
        job_id="job-1",
        scope=scope,
        partition="gs-1/search/search-v1",
    )
    assert writer.docs[0]["is_stale"] is True
```

- [ ] **Step 2: Implement search projection**

```python
# backend/app/services/semantic_search_projection.py
"""Search projection document builder + writer interface."""

from __future__ import annotations

from typing import Any, Protocol

from rdflib import Dataset, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_projection_job import ProjectionWriter
from app.services.semantic_read_scope import ScopeResolution


class SearchWriter(Protocol):
    def clear(self, partition: str) -> None: ...
    def write(self, partition: str, documents: list[dict[str, Any]]) -> None: ...


class FakeSearchWriter:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self.partition: str | None = None

    def clear(self, partition: str) -> None:
        self.docs = []
        self.partition = partition

    def write(self, partition: str, documents: list[dict[str, Any]]) -> None:
        self.partition = partition
        self.docs.extend(documents)


class SemanticSearchProjectionService(ProjectionWriter):
    kind = "search"

    def __init__(self, rdf_store: RdfStoreRepository, writer: SearchWriter) -> None:
        self.rdf_store = rdf_store
        self.writer = writer

    def rebuild(self, job_id: str, scope: ScopeResolution, partition: str) -> dict[str, int]:
        dataset = self._load_dataset(scope)
        documents = self._build_documents(dataset, scope)
        self.writer.clear(partition)
        self.writer.write(partition, documents)
        return {
            "node_count": 0,
            "relationship_count": 0,
            "document_count": len(documents),
        }

    def _load_dataset(self, scope: ScopeResolution) -> Dataset:
        dataset = Dataset()
        iris = list(scope.source_graph_iris)
        if scope.reasoning_result_graph_iri:
            iris.append(scope.reasoning_result_graph_iri)
        for iri in iris:
            content = self.rdf_store.get_graph(iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        return dataset

    def _build_documents(self, dataset: Dataset, scope: ScopeResolution) -> list[dict[str, Any]]:
        is_stale = any(
            scope.derived_state.get(kind, {}).get("status") == "stale"
            for kind in ("reasoning", "rule")
        )
        documents: list[dict[str, Any]] = []
        seen: set[str] = set()
        for subject, predicate, obj, graph in dataset.quads((None, None, None, None)):
            if not isinstance(subject, URIRef):
                continue
            iri = str(subject)
            if iri in seen:
                continue
            seen.add(iri)
            label = self._label(dataset, subject)
            comment = self._comment(dataset, subject)
            text_parts = [part for part in (label, comment) if part]
            documents.append({
                "id": iri,
                "iri": iri,
                "resource_kind": self._resource_kind(dataset, subject),
                "label": label,
                "text": " | ".join(text_parts),
                "assertion_kind": self._assertion_kind(str(graph), scope),
                "source_graph_iri": str(graph),
                "source_signature": scope.source_signature,
                "graph_set_id": scope.graph_set_id,
                "evidence_status": "unknown",
                "is_stale": is_stale,
                "visibility_labels": [],
            })
        return documents

    def _label(self, dataset: Dataset, subject: URIRef) -> str | None:
        for _, _, obj in dataset.quads((subject, RDFS.label, None, None)):
            return str(obj)
        return None

    def _comment(self, dataset: Dataset, subject: URIRef) -> str | None:
        for _, _, obj in dataset.quads((subject, RDFS.comment, None, None)):
            return str(obj)
        return None

    def _resource_kind(self, dataset: Dataset, subject: URIRef) -> str:
        for _, _, obj in dataset.quads((subject, RDF.type, None, None)):
            return str(obj)
        return "resource"

    def _assertion_kind(self, graph_iri: str, scope: ScopeResolution) -> str:
        if scope.reasoning_result_graph_iri and graph_iri == scope.reasoning_result_graph_iri:
            return "owl_inferred"
        if scope.rule_result_graph_iri and graph_iri == scope.rule_result_graph_iri:
            return "rule_derived"
        return "asserted"
```

- [ ] **Step 3: Write failing test for vector projection**

```python
# backend/tests/test_semantic_vector_projection.py
import hashlib

from app.services.semantic_read_scope import ScopeResolution
from app.services.semantic_vector_projection import (
    FakeVectorWriter,
    SemanticVectorProjectionService,
)


class FakeStore:
    def get_graph(self, iri, fmt):
        return """
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix ex: <http://example.test/> .
        ex:alice rdfs:label "Alice" ;
                 rdfs:comment "A student" .
        """


def _scope(iris):
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        source_graph_iris=iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=None,
        rule_result_graph_iri=None,
        derived_state={},
        warnings=[],
    )


def test_vector_documents_have_deterministic_ids_and_config_hash():
    writer = FakeVectorWriter()
    service = SemanticVectorProjectionService(
        rdf_store=FakeStore(),
        writer=writer,
        embedding_config={"model": "fake-embed", "version": "v1"},
    )
    counts = service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/vector/vector-v1",
    )
    assert counts["document_count"] == 1
    doc = writer.docs[0]
    expected_id = hashlib.sha256(
        f"gs-1|http://example.test/alice|resource|vector-v1".encode()
    ).hexdigest()
    assert doc["id"] == expected_id
    assert doc["embedding_config_hash"]
    assert doc["source_signature"] == "sig-1"
    assert doc["assertion_kind"] == "asserted"


def test_different_projection_version_changes_document_id():
    writer = FakeVectorWriter()
    service = SemanticVectorProjectionService(
        rdf_store=FakeStore(),
        writer=writer,
        embedding_config={"model": "fake-embed", "version": "v1"},
    )
    service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/vector/vector-v1",
    )
    first_id = writer.docs[0]["id"]
    writer.docs.clear()
    service = SemanticVectorProjectionService(
        rdf_store=FakeStore(),
        writer=writer,
        embedding_config={"model": "fake-embed", "version": "v2"},
    )
    service.rebuild(
        job_id="job-2",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/vector/vector-v2",
    )
    assert writer.docs[0]["id"] != first_id
```

- [ ] **Step 4: Implement vector projection**

```python
# backend/app/services/semantic_vector_projection.py
"""Vector projection document builder with deterministic ids and config hashes."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from rdflib import Dataset, URIRef
from rdflib.namespace import RDF, RDFS

from app.repositories.rdf_store import RdfFormat, RdfStoreRepository
from app.services.semantic_projection_job import ProjectionWriter
from app.services.semantic_read_scope import ScopeResolution


class VectorWriter(Protocol):
    def clear(self, partition: str) -> None: ...
    def write(self, partition: str, documents: list[dict[str, Any]]) -> None: ...


class FakeVectorWriter:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def clear(self, partition: str) -> None:
        self.docs = []

    def write(self, partition: str, documents: list[dict[str, Any]]) -> None:
        self.docs.extend(documents)


class SemanticVectorProjectionService(ProjectionWriter):
    kind = "vector"

    def __init__(
        self,
        rdf_store: RdfStoreRepository,
        writer: VectorWriter,
        embedding_config: dict[str, Any] | None = None,
    ) -> None:
        self.rdf_store = rdf_store
        self.writer = writer
        self.embedding_config = embedding_config or {"model": "default", "version": "v1"}

    def rebuild(self, job_id: str, scope: ScopeResolution, partition: str) -> dict[str, int]:
        dataset = self._load_dataset(scope)
        version = partition.rsplit("/", 1)[-1]
        documents = self._build_documents(dataset, scope, version)
        self.writer.clear(partition)
        self.writer.write(partition, documents)
        return {
            "node_count": 0,
            "relationship_count": 0,
            "document_count": len(documents),
        }

    def _load_dataset(self, scope: ScopeResolution) -> Dataset:
        dataset = Dataset()
        for iri in scope.source_graph_iris:
            content = self.rdf_store.get_graph(iri, RdfFormat.TRIG.value)
            if content:
                dataset.parse(data=content, format=RdfFormat.TRIG.value)
        return dataset

    def _build_documents(
        self,
        dataset: Dataset,
        scope: ScopeResolution,
        version: str,
    ) -> list[dict[str, Any]]:
        config_hash = self._config_hash()
        is_stale = any(
            scope.derived_state.get(kind, {}).get("status") == "stale"
            for kind in ("reasoning", "rule")
        )
        documents: list[dict[str, Any]] = []
        seen: set[str] = set()
        for subject, _, _, graph in dataset.quads((None, None, None, None)):
            if not isinstance(subject, URIRef):
                continue
            iri = str(subject)
            if iri in seen:
                continue
            seen.add(iri)
            label = self._label(dataset, subject)
            comment = self._comment(dataset, subject)
            text_parts = [part for part in (label, comment) if part]
            documents.append({
                "id": self._deterministic_id(scope.graph_set_id, iri, version),
                "iri": iri,
                "text": " | ".join(text_parts),
                "source_graph_iris": [str(graph)],
                "embedding_config_hash": config_hash,
                "embedding_config": dict(self.embedding_config),
                "source_signature": scope.source_signature,
                "graph_set_id": scope.graph_set_id,
                "assertion_kind": self._assertion_kind(str(graph), scope),
                "is_stale": is_stale,
                "visibility_labels": [],
            })
        return documents

    def _deterministic_id(self, graph_set_id: str, iri: str, version: str) -> str:
        return hashlib.sha256(f"{graph_set_id}|{iri}|resource|{version}".encode()).hexdigest()

    def _config_hash(self) -> str:
        serialised = "|".join(f"{k}={self.embedding_config.get(k)}" for k in sorted(self.embedding_config))
        return hashlib.sha256(serialised.encode()).hexdigest()

    def _label(self, dataset: Dataset, subject: URIRef) -> str | None:
        for _, _, obj in dataset.quads((subject, RDFS.label, None, None)):
            return str(obj)
        return None

    def _comment(self, dataset: Dataset, subject: URIRef) -> str | None:
        for _, _, obj in dataset.quads((subject, RDFS.comment, None, None)):
            return str(obj)
        return None

    def _assertion_kind(self, graph_iri: str, scope: ScopeResolution) -> str:
        if scope.reasoning_result_graph_iri and graph_iri == scope.reasoning_result_graph_iri:
            return "owl_inferred"
        if scope.rule_result_graph_iri and graph_iri == scope.rule_result_graph_iri:
            return "rule_derived"
        return "asserted"
```

- [ ] **Step 5: Run tests to verify**

```bash
cd backend && uv run pytest tests/test_semantic_search_projection.py tests/test_semantic_vector_projection.py -v
```

Expected: 4 passing tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/semantic_search_projection.py backend/app/services/semantic_vector_projection.py backend/tests/test_semantic_search_projection.py backend/tests/test_semantic_vector_projection.py
git commit -m "Add semantic phase 6 search and vector projection builders"
```

---

## Task 9: Light Visibility Policy

**Files:**
- Create: `backend/app/services/semantic_visibility.py`
- Test: `backend/tests/test_semantic_visibility.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_semantic_visibility.py
from app.services.semantic_visibility import (
    VisibilityDecision,
    SemanticVisibilityPolicy,
)


def test_unrestricted_graph_passes_through():
    policy = SemanticVisibilityPolicy(graph_labels={"http://op/s/graph/data/x": "internal"})
    decision = policy.evaluate(
        graph_iri="http://op/s/graph/data/x",
        visibility_context={"labels": ["internal"]},
    )
    assert decision.allow is True
    assert decision.redact_evidence is False


def test_restricted_graph_without_label_is_omitted():
    policy = SemanticVisibilityPolicy(
        graph_labels={"http://op/s/graph/data/secret": "restricted"}
    )
    decision = policy.evaluate(
        graph_iri="http://op/s/graph/data/secret",
        visibility_context={"labels": ["internal"]},
    )
    assert decision.allow is False


def test_restricted_graph_with_label_redacts_evidence():
    policy = SemanticVisibilityPolicy(
        graph_labels={"http://op/s/graph/data/secret": "restricted"}
    )
    decision = policy.evaluate(
        graph_iri="http://op/s/graph/data/secret",
        visibility_context={"labels": ["internal", "restricted"]},
    )
    assert decision.allow is True
    assert decision.redact_evidence is True


def test_filter_graphs_drops_unauthorized():
    policy = SemanticVisibilityPolicy(
        graph_labels={
            "http://op/s/graph/data/a": "internal",
            "http://op/s/graph/data/b": "restricted",
        }
    )
    allowed, warnings = policy.filter_graphs(
        [
            "http://op/s/graph/data/a",
            "http://op/s/graph/data/b",
        ],
        visibility_context={"labels": ["internal"]},
    )
    assert allowed == ["http://op/s/graph/data/a"]
    assert any("restricted" in w["message"] for w in warnings)


def test_redact_evidence_text_replaces_with_placeholder():
    policy = SemanticVisibilityPolicy(graph_labels={})
    assert policy.redact_evidence_text("Secret content") == "[redacted]"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && uv run pytest tests/test_semantic_visibility.py -v
```

Expected: collection error.

- [ ] **Step 3: Implement visibility policy**

```python
# backend/app/services/semantic_visibility.py
"""Light graph-set visibility labels and evidence redaction.

Phase 6 introduces conservative labels only — not full RBAC. Labels are
declared per graph IRI. A visibility context carries the labels the caller
already holds. Graphs whose label is not in the context are omitted; graphs
labelled `restricted` redact evidence text in read APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VisibilityDecision:
    allow: bool
    redact_evidence: bool


class SemanticVisibilityPolicy:
    redacted_marker = "[redacted]"

    def __init__(self, graph_labels: dict[str, str]) -> None:
        self.graph_labels = dict(graph_labels)

    def evaluate(self, graph_iri: str, visibility_context: dict[str, Any] | None) -> VisibilityDecision:
        labels = self._context_labels(visibility_context)
        required = self.graph_labels.get(graph_iri)
        if required is None:
            return VisibilityDecision(allow=True, redact_evidence=False)
        if required not in labels:
            return VisibilityDecision(allow=False, redact_evidence=False)
        if required == "restricted":
            return VisibilityDecision(allow=True, redact_evidence=True)
        return VisibilityDecision(allow=True, redact_evidence=False)

    def filter_graphs(
        self,
        graph_iris: list[str],
        visibility_context: dict[str, Any] | None,
    ) -> tuple[list[str], list[dict[str, str]]]:
        kept: list[str] = []
        warnings: list[dict[str, str]] = []
        for iri in graph_iris:
            decision = self.evaluate(iri, visibility_context)
            if decision.allow:
                kept.append(iri)
            else:
                label = self.graph_labels.get(iri, "restricted")
                warnings.append({
                    "code": "visibility_graph_omitted",
                    "message": f"Graph {iri} omitted (label={label}).",
                })
        return kept, warnings

    def redact_evidence_text(self, text: str | None) -> str | None:
        if text is None:
            return None
        return self.redacted_marker

    def _context_labels(self, visibility_context: dict[str, Any] | None) -> list[str]:
        if not visibility_context:
            return []
        labels = visibility_context.get("labels") or []
        return list(labels)
```

- [ ] **Step 4: Run tests to verify**

```bash
cd backend && uv run pytest tests/test_semantic_visibility.py -v
```

Expected: 5 passing tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_visibility.py backend/tests/test_semantic_visibility.py
git commit -m "Add semantic phase 6 light visibility policy"
```

---

## Task 10: Apply Visibility Policy to Read Models and Exports

**Files:**
- Modify: `backend/app/services/semantic_read_model.py`
- Modify: `backend/app/services/semantic_graph_set_export.py`
- Modify: `backend/tests/test_semantic_read_model.py`
- Modify: `backend/tests/test_semantic_export_graph_set.py`

- [ ] **Step 1: Extend read-model service test**

Append to `backend/tests/test_semantic_read_model.py`:

```python
def test_visibility_policy_filters_restricted_graphs():
    from app.services.semantic_visibility import SemanticVisibilityPolicy
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/data/a", "http://op/s/graph/data/b"]))
    store = FakeStore({
        "schema-summary": [
            {"class": "http://op/s/class/x", "label": "X", "graph": "http://op/s/graph/data/a"},
            {"class": "http://op/s/class/y", "label": "Y", "graph": "http://op/s/graph/data/b"},
        ]
    })
    policy = SemanticVisibilityPolicy(graph_labels={"http://op/s/graph/data/b": "restricted"})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=resolver,
        visibility_policy=policy,
    )
    envelope = service.read_model(
        "gs-1",
        "ontology-schema-summary",
        visibility_context={"labels": ["internal"]},
    )
    iris = {item["source_graph_iri"] for item in envelope["items"]}
    assert iris == {"http://op/s/graph/data/a"}
    assert any(w["code"] == "visibility_graph_omitted" for w in envelope["warnings"])
```

- [ ] **Step 2: Update read-model service to accept and apply policy**

Modify `SemanticReadModelService.__init__` to accept an optional `visibility_policy`. In `read_model`, after fetching items, filter rows whose `source_graph_iri` is not allowed and aggregate warnings.

```python
# In __init__, add:
        self.visibility_policy = visibility_policy

# In read_model, replace `items = [...]` block with:
        items: list[dict[str, Any]] = []
        warnings = list(scope.warnings)
        for row in self._rows(result):
            decorated = self._decorate_row(row, scope, template)
            if self.visibility_policy is not None:
                decision = self.visibility_policy.evaluate(
                    decorated["source_graph_iri"], visibility_context
                )
                if not decision.allow:
                    warnings.append({
                        "code": "visibility_graph_omitted",
                        "message": f"Graph {decorated['source_graph_iri']} omitted by visibility policy.",
                    })
                    continue
                if decision.redact_evidence:
                    decorated["evidence_ids"] = []
                    decorated["evidence_status"] = "not_applicable"
            items.append(decorated)
```

Add `visibility_context: dict[str, Any] | None = None` parameter to `read_model`.

- [ ] **Step 3: Update export service to accept visibility policy**

In `SemanticExportService.__init__`, accept `visibility_policy` parameter. In `export`, before loading graphs, filter `graph_iris` through `visibility_policy.filter_graphs` and append warnings.

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_semantic_read_model.py tests/test_semantic_export_graph_set.py -v
```

Expected: previous tests still pass; new visibility test passes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_read_model.py backend/app/services/semantic_graph_set_export.py backend/tests/test_semantic_read_model.py backend/tests/test_semantic_export_graph_set.py
git commit -m "Apply semantic phase 6 visibility policy to read models and exports"
```

---

## Task 11: API Endpoints for Read Models, Resources, Statements, Exports, Projection Jobs

**Files:**
- Modify: `backend/app/api/semantic.py`

- [ ] **Step 1: Add factory helpers and new routes**

In `backend/app/api/semantic.py`:

```python
# imports — add to existing block:
from app.api.schemas import (
    # ... existing imports ...
    SemanticExportRequest,
    SemanticProjectionJobCreate,
    SemanticProjectionJobRead,
    SemanticProjectionJobListResponse,
    SemanticProjectionManifestRead,
    SemanticProjectionReconcileResponse,
    SemanticProjectionStatusResponse,
    SemanticReadModelEnvelope,
    SemanticResourceRead,
    SemanticStatementItem,
)
from app.services.semantic_graph_set_export import ExportError, SemanticExportService
from app.services.semantic_neo4j_projection import Neo4jSemanticProjectionService
from app.services.semantic_projection_job import (
    ProjectionJobError,
    SemanticProjectionJobService,
)
from app.services.semantic_read_model import ReadModelError, SemanticReadModelService
from app.services.semantic_read_scope import (
    ReadScopeError,
    SemanticReadScopeResolver,
)
from app.services.semantic_search_projection import (
    FakeSearchWriter,
    SemanticSearchProjectionService,
)
from app.services.semantic_vector_projection import (
    FakeVectorWriter,
    SemanticVectorProjectionService,
)
from app.services.semantic_visibility import SemanticVisibilityPolicy


# factory helpers ----------------------------------------------------------
def _scope_resolver(session: Session) -> SemanticReadScopeResolver:
    return SemanticReadScopeResolver(session)


def _read_model_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> SemanticReadModelService:
    return SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=_scope_resolver(session),
        visibility_policy=SemanticVisibilityPolicy(
            graph_labels=settings.semantic_graph_visibility_labels
            if hasattr(settings, "semantic_graph_visibility_labels")
            else {}
        ),
    )


def _export_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> SemanticExportService:
    return SemanticExportService(
        rdf_store=rdf_store,
        scope_resolver=_scope_resolver(session),
        settings=settings,
    )


def _projection_job_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    driver: Driver | None,
    settings: Settings,
) -> SemanticProjectionJobService:
    writers: dict[str, object] = {
        "neo4j": Neo4jSemanticProjectionService(rdf_store, driver),
        "search": SemanticSearchProjectionService(rdf_store, FakeSearchWriter()),
        "vector": SemanticVectorProjectionService(rdf_store, FakeVectorWriter()),
    }
    return SemanticProjectionJobService(
        session=session,
        writers=writers,
        scope_resolver_builder=_scope_resolver,
    )


# routes -------------------------------------------------------------------
@router.get(
    "/graph-sets/{graph_set_id}/read-models/{model_name}",
    response_model=SemanticReadModelEnvelope,
)
def read_model(
    graph_set_id: str,
    model_name: str,
    include: Annotated[str, Query()] = "asserted",
    allow_stale_derived: Annotated[bool, Query()] = True,
    field_set: Annotated[str, Query()] = "summary",
    limit: Annotated[int | None, Query(ge=1, le=2000)] = None,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReadModelEnvelope:
    service = _read_model_service(session, rdf_store, settings)
    try:
        envelope = service.read_model(
            graph_set_id=graph_set_id,
            model_name=model_name,
            include=include,
            allow_stale_derived=allow_stale_derived,
            limit=limit,
            field_set=field_set,
        )
    except (ReadModelError, ReadScopeError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return SemanticReadModelEnvelope(**envelope)


@router.get("/resources/{resource_iri:path}", response_model=SemanticResourceRead)
def read_resource(
    resource_iri: str,
    graph_set_id: Annotated[str | None, Query()] = None,
    include: Annotated[str, Query()] = "asserted",
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticResourceRead:
    if graph_set_id is None:
        raise HTTPException(status_code=400, detail="graph_set_id query parameter is required")
    service = _read_model_service(session, rdf_store, settings)
    envelope = service.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-detail",
        include=include,
    )
    for item in envelope["items"]:
        if item["iri"] == resource_iri:
            return SemanticResourceRead(
                iri=resource_iri,
                label=item.get("label"),
                graph_set_id=graph_set_id,
                source_signature=envelope["source_signature"],
                assertion_kind=item["assertion_kind"],
                evidence_status=item["evidence_status"],
                source_graph_iri=item["source_graph_iri"],
                properties={},
                derived_state=envelope["derived_state"],
                warnings=envelope["warnings"],
            )
    raise HTTPException(status_code=404, detail=f"Resource not found: {resource_iri}")


@router.get("/statements", response_model=SemanticReadModelEnvelope)
def list_statements(
    graph_set_id: Annotated[str, Query()],
    include: Annotated[str, Query()] = "asserted",
    allow_stale_derived: Annotated[bool, Query()] = True,
    limit: Annotated[int | None, Query(ge=1, le=5000)] = None,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReadModelEnvelope:
    service = _read_model_service(session, rdf_store, settings)
    envelope = service.read_model(
        graph_set_id=graph_set_id,
        model_name="statement-list",
        include=include,
        allow_stale_derived=allow_stale_derived,
        limit=limit,
    )
    return SemanticReadModelEnvelope(**envelope)


@router.get("/graph-sets/{graph_set_id}/export")
def export_graph_set(
    graph_set_id: str,
    format: Annotated[str, Query()] = "trig",
    include: Annotated[str, Query()] = "asserted",
    include_evidence: Annotated[bool, Query()] = False,
    include_shapes: Annotated[bool, Query()] = False,
    include_policy: Annotated[bool, Query()] = False,
    include_metadata: Annotated[bool, Query()] = False,
    allow_stale_derived: Annotated[bool, Query()] = False,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    service = _export_service(session, rdf_store, settings)
    try:
        payload, _warnings = service.export(
            graph_set_id=graph_set_id,
            format=format,
            include=include,
            include_evidence=include_evidence,
            include_shapes=include_shapes,
            include_policy=include_policy,
            include_metadata=include_metadata,
            allow_stale_derived=allow_stale_derived,
        )
    except (ExportError, ReadScopeError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    media_type = {
        "trig": "application/trig",
        "json-ld": "application/ld+json",
        "turtle": "text/turtle",
    }[format]
    return Response(content=payload, media_type=media_type)


@router.post(
    "/graph-sets/{graph_set_id}/projection-jobs",
    response_model=SemanticProjectionJobRead,
    status_code=201,
)
def create_projection_job_for_set(
    graph_set_id: str,
    request: SemanticProjectionJobCreate,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    if request.graph_set_id != graph_set_id:
        raise HTTPException(status_code=400, detail="graph_set_id in body must match path")
    service = _projection_job_service(session, rdf_store, driver, settings)
    try:
        job = service.create_job(
            graph_set_id=request.graph_set_id,
            projection_kind=request.projection_kind,
            projection_version=request.projection_version,
            include=request.include,
            mode=request.mode,
            target_partition=request.target_partition,
            allow_stale_derived=request.allow_stale_derived,
            metadata=request.metadata,
        )
    except ProjectionJobError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return _projection_job_read(job)


@router.get("/projection-jobs", response_model=SemanticProjectionJobListResponse)
def list_projection_jobs(
    graph_set_id: Annotated[str | None, Query()] = None,
    projection_kind: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobListResponse:
    service = _projection_job_service(session, rdf_store, driver, settings)
    jobs = service.list_jobs(graph_set_id=graph_set_id, projection_kind=projection_kind, status=status)
    items = [_projection_job_read(j) for j in jobs]
    return SemanticProjectionJobListResponse(items=items, total=len(items))


@router.get("/projection-jobs/{job_id}", response_model=SemanticProjectionJobRead)
def get_projection_job(
    job_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    service = _projection_job_service(session, rdf_store, driver, settings)
    try:
        job = service.get_job(job_id)
    except ProjectionJobError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    return _projection_job_read(job)


@router.post("/projection-jobs/{job_id}:run", response_model=SemanticProjectionJobRead)
def run_projection_job(
    job_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    service = _projection_job_service(session, rdf_store, driver, settings)
    try:
        job = service.run_job(job_id)
    except ProjectionJobError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return _projection_job_read(job)


@router.post("/projections:reconcile", response_model=SemanticProjectionReconcileResponse)
def reconcile_projections(
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionReconcileResponse:
    service = _projection_job_service(session, rdf_store, driver, settings)
    report = service.reconcile()
    return SemanticProjectionReconcileResponse(**report)


@router.get("/projections/status", response_model=SemanticProjectionStatusResponse)
def projection_status(
    graph_set_id: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionStatusResponse:
    service = _projection_job_service(session, rdf_store, driver, settings)
    status = service.status(graph_set_id=graph_set_id)
    return SemanticProjectionStatusResponse(**status)


def _projection_job_read(job) -> SemanticProjectionJobRead:
    return SemanticProjectionJobRead(
        id=job.id,
        graph_set_id=job.graph_set_id,
        projection_kind=job.projection_kind,
        projection_version=job.projection_version,
        projection_scope=job.projection_scope,
        source_signature=job.source_signature,
        input_graph_revisions=job.input_graph_revisions or {},
        input_derived_pointers=job.input_derived_pointers or {},
        target_store=job.target_store,
        target_partition=job.target_partition,
        status=job.status,
        node_count=job.node_count,
        relationship_count=job.relationship_count,
        document_count=job.document_count,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        metadata=job.job_metadata or {},
    )
```

- [ ] **Step 2: Add `semantic_graph_visibility_labels` setting if missing**

In `backend/app/core/config.py`, if `semantic_graph_visibility_labels` is not already on `Settings`, add:

```python
    semantic_graph_visibility_labels: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 3: Verify imports**

```bash
cd backend && uv run python -c "from app.api.semantic import router; print(len(router.routes))"
```

Expected: prints a number; no import errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/semantic.py backend/app/core/config.py
git commit -m "Add semantic phase 6 read model, export, and projection job endpoints"
```

---

## Task 12: API Tests for Phase 6 Endpoints

**Files:**
- Create: `backend/tests/test_semantic_phase6_api.py`
- Modify: `backend/tests/test_semantic_api.py` (only if existing projection response test breaks)

- [ ] **Step 1: Write API tests**

```python
# backend/tests/test_semantic_phase6_api.py
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import create_app


def _seed_graph_set(session, graph_iris):
    from app.repositories.models import (
        SemanticGraphSetMemberModel,
        SemanticGraphSetModel,
    )
    gs = SemanticGraphSetModel(
        id="gs-1",
        name="demo",
        scope_type="ontology_version",
        scope_id="ov-1",
        status="active",
        source_signature="sig-1",
    )
    session.add(gs)
    for idx, iri in enumerate(graph_iris):
        gs.members.append(
            SemanticGraphSetMemberModel(
                id=f"m-{idx}",
                graph_iri=iri,
                role="asserted_data" if idx == 0 else "shape",
                required=True,
                sort_order=idx,
            )
        )
    session.commit()


def _install_fakes(monkeypatch, store_payloads, scope_resolution=None):
    from app.api import semantic as semantic_api
    from app.services.semantic_read_scope import ScopeResolution

    if scope_resolution is None:
        scope_resolution = ScopeResolution(
            graph_set_id="gs-1",
            source_signature="sig-1",
            include="asserted",
            source_graph_iris=["http://op/s/graph/data/ov-1"],
            shape_graph_iris=[],
            governance_graph_iris=[],
            reasoning_result_graph_iri=None,
            rule_result_graph_iri=None,
            derived_state={},
            warnings=[],
        )

    class FakeStore:
        def get_graph(self, iri, fmt):
            return store_payloads.get(iri, "")

        def query_read_model(self, query, graph_iris, timeout_seconds, limit):
            class R:
                bindings = store_payloads.get("__rows__", [])
            return R()

    fake_store = FakeStore()

    class FakeResolver:
        def resolve(self, graph_set_id, include="asserted", allow_stale_derived=True):
            return scope_resolution

    monkeypatch.setattr(semantic_api, "get_rdf_store", lambda: fake_store)
    monkeypatch.setattr(semantic_api, "_scope_resolver", lambda session: FakeResolver())


def test_read_model_endpoint_returns_envelope(test_client, session_factory, monkeypatch):
    with session_factory() as session:
        _seed_graph_set(session, ["http://op/s/graph/data/ov-1"])
    _install_fakes(
        monkeypatch,
        {
            "__rows__": [
                {"class": "http://op/s/class/x", "label": "X", "graph": "http://op/s/graph/data/ov-1"}
            ]
        },
    )
    response = test_client.get(
        "/api/semantic/graph-sets/gs-1/read-models/ontology-schema-summary",
        params={"include": "asserted"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["graph_set_id"] == "gs-1"
    assert body["items"][0]["assertion_kind"] == "asserted"


def test_export_endpoint_returns_trig(test_client, session_factory, monkeypatch):
    with session_factory() as session:
        _seed_graph_set(session, ["http://op/s/graph/data/ov-1"])
    _install_fakes(
        monkeypatch,
        {"http://op/s/graph/data/ov-1": "@prefix ex: <http://example.test/> . <http://op/s/graph/data/ov-1> { ex:a ex:b ex:c . }"},
    )
    response = test_client.get(
        "/api/semantic/graph-sets/gs-1/export",
        params={"format": "trig"},
    )
    assert response.status_code == 200
    assert "application/trig" in response.headers["content-type"]


def test_export_turtle_rejects_multi_graph(test_client, session_factory, monkeypatch):
    with session_factory() as session:
        _seed_graph_set(session, ["http://op/s/graph/data/ov-1", "http://op/s/graph/shapes/ov-1"])
    _install_fakes(
        monkeypatch,
        {
            "http://op/s/graph/data/ov-1": "@prefix ex: <http://example.test/> . ex:a ex:b ex:c .",
            "http://op/s/graph/shapes/ov-1": '@prefix ex: <http://example.test/> . ex:x ex:y ex:z .',
        },
    )
    response = test_client.get(
        "/api/semantic/graph-sets/gs-1/export",
        params={"format": "turtle"},
    )
    assert response.status_code == 400


def test_projection_job_lifecycle(test_client, session_factory, monkeypatch):
    with session_factory() as session:
        _seed_graph_set(session, ["http://op/s/graph/data/ov-1"])
    _install_fakes(monkeypatch, {})

    create = test_client.post(
        "/api/semantic/graph-sets/gs-1/projection-jobs",
        json={
            "graph_set_id": "gs-1",
            "projection_kind": "neo4j",
            "projection_version": "neo4j-v1",
            "include": "asserted",
            "mode": "rebuild",
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    run = test_client.post(f"/api/semantic/projection-jobs/{job_id}:run")
    assert run.status_code == 200
    assert run.json()["status"] == "succeeded"

    status = test_client.get("/api/semantic/projections/status", params={"graph_set_id": "gs-1"})
    assert status.status_code == 200
    assert any(m["projection_kind"] == "neo4j" for m in status.json()["manifests"])


def test_projection_reconcile_endpoint(test_client, session_factory, monkeypatch):
    with session_factory() as session:
        _seed_graph_set(session, ["http://op/s/graph/data/ov-1"])
    _install_fakes(monkeypatch, {})
    response = test_client.post("/api/semantic/projections:reconcile")
    assert response.status_code == 200
    assert "reconciled" in response.json()
```

Notes on the test scaffolding (test_client / session_factory fixtures):
- These fixtures already exist in `backend/tests/conftest.py` from earlier phases. Verify before writing tests.
- If `test_client` does not exist, use `from app.main import create_app` and build `TestClient(create_app())` per test, overriding `get_rdf_store` and `get_db_session` via dependency_overrides.

- [ ] **Step 2: Run tests**

```bash
cd backend && uv run pytest tests/test_semantic_phase6_api.py -v
```

Expected: 5 passing tests.

If fixtures are missing, inspect `backend/tests/conftest.py` for existing fixtures (`client`, `session`, etc.) and adapt.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_semantic_phase6_api.py
git commit -m "Add semantic phase 6 API tests"
```

---

## Task 13: MCP Tools for Stable Read/Export/Projection Workflows

**Files:**
- Modify: `backend/app/mcp/tools/semantic.py`
- Modify: `backend/tests/test_mcp_surface.py`

- [ ] **Step 1: Identify the existing MCP registration pattern**

Open `backend/app/mcp/tools/semantic.py` and read the first 80 lines to find:
- How `register_semantic(server)` adds tools.
- How existing tools retrieve dependencies (DB session, rdf_store, settings).

- [ ] **Step 2: Add five new MCP tools**

Inside `register_semantic`, add tools (using the same dependency-injection style as the existing tools):

```python
@mcp.tool()
def get_semantic_read_model(
    graph_set_id: str,
    model_name: str,
    include: str = "asserted",
    allow_stale_derived: bool = True,
) -> dict:
    """Read a compact graph-derived business JSON read model for a graph set."""
    from app.services.semantic_read_model import ReadModelError, SemanticReadModelService
    from app.services.semantic_read_scope import ReadScopeError, SemanticReadScopeResolver

    with get_session() as session:
        rdf_store = build_rdf_store()
        service = SemanticReadModelService(
            rdf_store=rdf_store,
            scope_resolver=SemanticReadScopeResolver(session),
        )
        try:
            return service.read_model(
                graph_set_id=graph_set_id,
                model_name=model_name,
                include=include,
                allow_stale_derived=allow_stale_derived,
            )
        except (ReadModelError, ReadScopeError) as exc:
            return {"error": str(exc), "status_code": getattr(exc, "status_code", 400)}


@mcp.tool()
def export_semantic_graph_set(
    graph_set_id: str,
    format: str = "trig",
    include: str = "asserted",
    allow_stale_derived: bool = False,
) -> dict:
    """Export a graph set as Turtle, TriG, or JSON-LD."""
    from app.services.semantic_graph_set_export import ExportError, SemanticExportService
    from app.services.semantic_read_scope import SemanticReadScopeResolver

    with get_session() as session:
        service = SemanticExportService(
            rdf_store=build_rdf_store(),
            scope_resolver=SemanticReadScopeResolver(session),
            settings=get_settings(),
        )
        try:
            payload, warnings = service.export(
                graph_set_id=graph_set_id,
                format=format,
                include=include,
                allow_stale_derived=allow_stale_derived,
            )
        except (ExportError, Exception) as exc:
            return {"error": str(exc), "status_code": getattr(exc, "status_code", 400)}
        return {"format": format, "payload": payload, "warnings": warnings}


@mcp.tool()
def inspect_semantic_projection_status(graph_set_id: str | None = None) -> dict:
    """Inspect projection freshness by graph set and projection kind."""
    from app.services.semantic_projection_job import SemanticProjectionJobService
    from app.services.semantic_read_scope import SemanticReadScopeResolver

    with get_session() as session:
        service = SemanticProjectionJobService(
            session=session,
            writers={},
            scope_resolver_builder=SemanticReadScopeResolver,
        )
        return service.status(graph_set_id=graph_set_id)


@mcp.tool()
def start_semantic_projection_job(
    graph_set_id: str,
    projection_kind: str,
    projection_version: str,
    include: str = "asserted",
    mode: str = "rebuild",
    allow_stale_derived: bool = False,
) -> dict:
    """Request a projection rebuild job."""
    from app.services.semantic_neo4j_projection import Neo4jSemanticProjectionService
    from app.services.semantic_projection_job import (
        ProjectionJobError,
        SemanticProjectionJobService,
    )
    from app.services.semantic_read_scope import SemanticReadScopeResolver
    from app.services.semantic_search_projection import (
        FakeSearchWriter,
        SemanticSearchProjectionService,
    )
    from app.services.semantic_vector_projection import (
        FakeVectorWriter,
        SemanticVectorProjectionService,
    )

    settings = get_settings()
    rdf_store = build_rdf_store()
    with get_session() as session:
        writers = {
            "neo4j": Neo4jSemanticProjectionService(rdf_store, None),
            "search": SemanticSearchProjectionService(rdf_store, FakeSearchWriter()),
            "vector": SemanticVectorProjectionService(rdf_store, FakeVectorWriter()),
        }
        service = SemanticProjectionJobService(
            session=session,
            writers=writers,
            scope_resolver_builder=SemanticReadScopeResolver,
        )
        try:
            job = service.create_job(
                graph_set_id=graph_set_id,
                projection_kind=projection_kind,
                projection_version=projection_version,
                include=include,
                mode=mode,
                allow_stale_derived=allow_stale_derived,
            )
            if mode != "dry_run":
                service.run_job(job.id)
            refreshed = service.get_job(job.id)
        except ProjectionJobError as exc:
            return {"error": str(exc), "status_code": getattr(exc, "status_code", 400)}
        return {
            "id": refreshed.id,
            "status": refreshed.status,
            "projection_kind": refreshed.projection_kind,
            "node_count": refreshed.node_count,
            "relationship_count": refreshed.relationship_count,
            "document_count": refreshed.document_count,
        }


@mcp.tool()
def inspect_semantic_statement_provenance(
    graph_set_id: str,
    statement_iri: str,
    include: str = "asserted",
) -> dict:
    """Inspect provenance, evidence, assertion kind, and staleness for a statement."""
    from app.services.semantic_read_model import SemanticReadModelService
    from app.services.semantic_read_scope import SemanticReadScopeResolver

    with get_session() as session:
        service = SemanticReadModelService(
            rdf_store=build_rdf_store(),
            scope_resolver=SemanticReadScopeResolver(session),
        )
        envelope = service.read_model(
            graph_set_id=graph_set_id,
            model_name="statement-list",
            include=include,
        )
        for item in envelope["items"]:
            if item["iri"] == statement_iri:
                return item
        return {"error": "statement not found", "graph_set_id": graph_set_id, "iri": statement_iri}
```

The exact dependency-injection pattern (`get_session`, `build_rdf_store`, `get_settings`) varies — copy the style from an existing tool in the same file.

- [ ] **Step 3: Update test_mcp_surface.py**

In `backend/tests/test_mcp_surface.py`, find the list of expected tool names and add:

```python
"get_semantic_read_model",
"export_semantic_graph_set",
"inspect_semantic_projection_status",
"start_semantic_projection_job",
"inspect_semantic_statement_provenance",
```

- [ ] **Step 4: Run MCP tests**

```bash
cd backend && uv run pytest tests/test_mcp_surface.py tests/test_mcp_payloads.py -v
```

Expected: passing.

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp/tools/semantic.py backend/tests/test_mcp_surface.py
git commit -m "Add semantic phase 6 MCP tools for read models and projections"
```

---

## Task 14: Update Plan Document and Run Full Backend Suite

**Files:**
- Modify: `semantic-language-refactor-plan.md`

- [ ] **Step 1: Update Phase 6 progress marker**

In `semantic-language-refactor-plan.md`, locate the "Current Progress" section and add lines:

```markdown
- Phase 6 design: completed in
  `docs/architecture/semantic/phase6-graph-derived-product-apis-projections.md`.
- Implementation: Phase 6 graph-derived read models, JSON-LD/Turtle/TriG export,
  projection jobs and manifests, Neo4j/search/vector projection writers, light
  visibility policy, and MCP tools implemented and covered by backend tests.
```

- [ ] **Step 2: Run full backend test suite**

```bash
cd backend && uv run pytest -x
```

Expected: full suite passes (existing tests + new Phase 6 tests).

- [ ] **Step 3: Commit**

```bash
git add semantic-language-refactor-plan.md
git commit -m "Mark semantic phase 6 implementation complete in plan"
```

---

## Self-Review Notes

**Spec coverage check (against `docs/architecture/semantic/phase6-graph-derived-product-apis-projections.md`):**

- ✅ Compact business JSON read models — Task 4 + Task 11
- ✅ JSON-LD resource/read-model responses — Task 5 + Task 11 (`/resources/{iri}`)
- ✅ Turtle/TriG export — Task 5 + Task 11
- ✅ Projection job metadata and manifests — Task 2 + Task 6
- ✅ Projection staleness reconciliation — Task 6 (`reconcile`)
- ✅ Neo4j partition-scoped projection writer — Task 7
- ✅ Graph visualization reads only from current manifest — Task 6 enforces manifest status; Task 11 surfaces via `/projections/status`
- ✅ Search document projection — Task 8
- ✅ Vector document projection with embedding config/version — Task 8
- ✅ Light visibility policy — Task 9 + Task 10
- ✅ MCP tools for stable workflows — Task 13
- ✅ Tests independent of live external services — all task tests use fakes

**Out of scope / deferred (acknowledged):**

- Real Neo4j driver integration tests (smoke only — Phase 6 acceptance says "tests or smoke checks"). Tasks 7 and 12 use FakeDriver.
- Real search/vector store adapters — Task 8 ships `Fake*Writer` per the design's "no live external services" rule. Production adapters are Phase 7 work.
- `rebuild_side_by_side` mode — listed in design but tests only assert `dry_run` and `rebuild`; full side-by-side verification is Phase 7.

**Type consistency check:**

- `ScopeResolution` is shared across Tasks 1, 4, 5, 6, 7, 8 — same dataclass throughout.
- `ProjectionWriter` Protocol (Task 6) is implemented by `Neo4jSemanticProjectionService` (Task 7), `SemanticSearchProjectionService` (Task 8), `SemanticVectorProjectionService` (Task 8) — all expose `kind` and `rebuild(job_id, scope, partition)`.
- `SemanticProjectionJobService` returns SQLAlchemy models; `_projection_job_read` adapter normalises to Pydantic in Task 11.
- Manifest dict shape (`_manifest_dict` in Task 6) matches `SemanticProjectionManifestRead` fields in Task 3.
