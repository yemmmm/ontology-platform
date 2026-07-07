# Evidence → Postgres Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move evidence storage from RDF triple store to Postgres at fact_id (sha256(s,p,o,g)) granularity, make `missing_evidence` a derived state, and clean up all legacy dead code.

**Architecture:** New `fact_evidence_bindings` PG table + repository + new bind/unbind commands + new read path that batch-queries PG. Then delete legacy `op:evidenceStatus`, `prov:wasDerivedFrom` literals, reified `op:FactClaim`, and 4 old commands. Frontend gets a new PDF chunk picker.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy 2.0, Alembic, rdflib, pytest; React 18, TypeScript, Vite, vitest.

**Spec:** `docs/superpowers/specs/2026-07-08-evidence-postgres-refactor-design.md`

---

## File Structure

**New files (7):**
- `backend/app/services/fact_id.py` — canonical fact_id util (4-tuple sha256)
- `backend/app/repositories/fact_evidence_repository.py` — PG CRUD
- `backend/app/api/fact_evidence.py` — REST endpoints
- `backend/migrations/versions/0018_fact_evidence_bindings.py` — schema migration
- `backend/scripts/cleanup_legacy_evidence_rdf.py` — one-shot cleanup
- `frontend/src/components/semantic/EvidenceChunkPicker.tsx` — UI picker
- Test files for each new module

**Deleted files (2):**
- `backend/app/services/semantic_missing_evidence.py`
- `frontend/src/components/semantic/EvidenceBindingPanel.tsx`

**Modified files (~20):**
- Backend: `semantic_command_compiler.py`, `semantic_read_model.py`, `semantic_sparql_templates.py`, `semantic_reasoning.py`, `semantic_validation.py`, `semantic_rule_execution.py`, `semantic_build_overview.py`, `semantic_migration.py`, `semantic.py`, `api/semantic.py`, `api/schemas.py`, `mcp/tools/semantic.py`, `repositories/models.py`
- Frontend: `pages/FactAuditPage.tsx`, `pages/GraphSetPage.tsx`, `pages/GraphGovernancePage.tsx`, `pages/SemanticEditWorkbenchPage.tsx`, `pages/SemanticImportExportPage.tsx`, `components/semantic/EvidenceExplorerPanel.tsx`, `components/semantic/badges.tsx`, `semanticApi.ts`, `types.ts`, `i18n/zh.ts`

---

## Phase 1: Infrastructure (Tasks 1-3)

### Task 1: Create `fact_id.py` util

**Files:**
- Create: `backend/app/services/fact_id.py`
- Create: `backend/tests/test_fact_id.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_fact_id.py
from app.services.fact_id import compute_fact_id, canonical_object_term

def test_canonical_object_term_iri():
    assert canonical_object_term("http://example.org/x", is_iri=True) == "<http://example.org/x>"

def test_canonical_object_term_string_literal():
    assert canonical_object_term("hello", is_iri=False) == '"hello"'

def test_canonical_object_term_typed_literal():
    term = canonical_object_term("42", is_iri=False, datatype="http://www.w3.org/2001/XMLSchema#integer")
    assert term == '"42"^^<http://www.w3.org/2001/XMLSchema#integer>'

def test_compute_fact_id_is_stable_4_tuple():
    fid1 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g")
    fid2 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g")
    assert fid1 == fid2
    assert len(fid1) == 64

def test_compute_fact_id_changes_with_graph():
    fid1 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g1")
    fid2 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g2")
    assert fid1 != fid2

def test_compute_fact_id_changes_with_object():
    fid1 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g")
    fid2 = compute_fact_id("http://a/s", "http://a/p", '"43"', "http://a/g")
    assert fid1 != fid2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_fact_id.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.fact_id`

- [ ] **Step 3: Write implementation**

```python
# backend/app/services/fact_id.py
"""Canonical fact_id computation (4-tuple sha256)."""
import hashlib


def canonical_object_term(
    value: str,
    *,
    is_iri: bool = False,
    datatype: str | None = None,
    lang: str | None = None,
) -> str:
    """Render object value as N-Triples term."""
    if is_iri:
        return f"<{value}>"
    if lang:
        return f'"{value}"@{lang}'
    if datatype:
        return f'"{value}"^^<{datatype}>'
    return f'"{value}"'


def compute_fact_id(
    subject_iri: str,
    predicate_iri: str,
    object_ntriples: str,
    graph_iri: str,
) -> str:
    """SHA-256 hex over canonical N-Triples-style (s, p, o, g) tuple.

    Object term must already be N-Triples serialized (use canonical_object_term).
    """
    canonical = f"<{subject_iri}> <{predicate_iri}> {object_ntriples} <{graph_iri}>"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_fact_id.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fact_id.py backend/tests/test_fact_id.py
git commit -m "feat(semantic): add canonical fact_id util (4-tuple sha256)"
```

---

### Task 2: Add `FactEvidenceBindingModel` + Alembic migration

**Files:**
- Modify: `backend/app/repositories/models.py` (append new class)
- Create: `backend/migrations/versions/0018_fact_evidence_bindings.py`

- [ ] **Step 1: Add model class**

Append to `backend/app/repositories/models.py` (after `EvidenceChunkModel`):

```python
class FactEvidenceBindingModel(Base):
    """Fact-level evidence binding stored in Postgres.

    Each row binds one piece of evidence (chunk reference or raw text) to a
    specific fact identified by fact_id (sha256(s,p,o,g)). Replaces the
    legacy RDF prov:wasDerivedFrom + chunk literal pattern.
    """
    __tablename__ = "fact_evidence_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fact_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_iri: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    predicate_iri: Mapped[str] = mapped_column(Text, nullable=False)
    object_value: Mapped[str] = mapped_column(Text, nullable=False)
    graph_iri: Mapped[str] = mapped_column(Text, nullable=False)

    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_chunks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_artifacts.id", ondelete="SET NULL"), nullable=True
    )

    document_filename: Mapped[str | None] = mapped_column(String(255))
    sequence: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    actor: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 2: Create Alembic migration**

```python
# backend/migrations/versions/0018_fact_evidence_bindings.py
"""Add fact_evidence_bindings table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_fact_evidence_bindings"
down_revision: str | None = "0017_drop_legacy_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_evidence_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fact_id", sa.String(length=64), nullable=False),
        sa.Column("subject_iri", sa.Text(), nullable=False),
        sa.Column("predicate_iri", sa.Text(), nullable=False),
        sa.Column("object_value", sa.Text(), nullable=False),
        sa.Column("graph_iri", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("document_filename", sa.String(length=255), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["evidence_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evidence_artifact_id"], ["evidence_artifacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_evidence_bindings_fact_id", "fact_evidence_bindings", ["fact_id"])
    op.create_index("ix_fact_evidence_bindings_subject_iri", "fact_evidence_bindings", ["subject_iri"])
    op.create_index(
        "ix_fact_evidence_bindings_chunk_id",
        "fact_evidence_bindings",
        ["chunk_id"],
        postgresql_where=sa.text("chunk_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_fact_evidence_bindings_chunk_id", table_name="fact_evidence_bindings")
    op.drop_index("ix_fact_evidence_bindings_subject_iri", table_name="fact_evidence_bindings")
    op.drop_index("ix_fact_evidence_bindings_fact_id", table_name="fact_evidence_bindings")
    op.drop_table("fact_evidence_bindings")
```

- [ ] **Step 3: Apply migration**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade 0017 -> 0018, Add fact_evidence_bindings table`

- [ ] **Step 4: Verify table exists**

Run: `cd backend && uv run python -c "from sqlalchemy import create_engine, inspect; import os; e=create_engine(os.environ['DATABASE_URL']); print([t for t in inspect(e).get_table_names() if 'fact_evidence' in t])"`
Expected: `['fact_evidence_bindings']`

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/models.py backend/migrations/versions/0018_fact_evidence_bindings.py
git commit -m "feat(db): add fact_evidence_bindings table"
```

---

### Task 3: Create `FactEvidenceBindingRepository`

**Files:**
- Create: `backend/app/repositories/fact_evidence_repository.py`
- Create: `backend/tests/test_fact_evidence_repository.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_fact_evidence_repository.py
from datetime import datetime
from uuid import uuid4

from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
from app.repositories.models import FactEvidenceBindingModel


def test_create_and_list_by_fact_id(db_session):
    repo = FactEvidenceBindingRepository(db_session)
    binding = repo.create(
        fact_id="a" * 64,
        subject_iri="http://example/s",
        predicate_iri="http://example/p",
        object_value='"42"',
        graph_iri="http://example/g",
        text="evidence text",
        actor="user:alice",
    )
    assert binding.id
    assert binding.fact_id == "a" * 64
    assert binding.text == "evidence text"

    listed = repo.list_by_fact_id("a" * 64)
    assert len(listed) == 1
    assert listed[0].text == "evidence text"


def test_list_by_fact_ids_batch(db_session):
    repo = FactEvidenceBindingRepository(db_session)
    for fact_id in ["f1" * 32, "f2" * 32]:
        repo.create(
            fact_id=fact_id, subject_iri="s", predicate_iri="p",
            object_value='"v"', graph_iri="g", text="t",
        )
    result = repo.list_by_fact_ids(["f1" * 32, "f2" * 32, "f3" * 32])
    assert set(result.keys()) == {"f1" * 32, "f2" * 32}
    assert len(result["f1" * 32]) == 1


def test_count_facts_with_bindings(db_session):
    repo = FactEvidenceBindingRepository(db_session)
    repo.create(fact_id="a" * 64, subject_iri="s", predicate_iri="p",
                object_value='"v"', graph_iri="g", text="t")
    result = repo.count_facts_with_bindings(["a" * 64, "b" * 64])
    assert result == {"a" * 64}


def test_delete(db_session):
    repo = FactEvidenceBindingRepository(db_session)
    binding = repo.create(fact_id="a" * 64, subject_iri="s", predicate_iri="p",
                          object_value='"v"', graph_iri="g", text="t")
    assert repo.delete(binding.id) is True
    assert repo.delete(binding.id) is False
    assert repo.list_by_fact_id("a" * 64) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_fact_evidence_repository.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# backend/app/repositories/fact_evidence_repository.py
"""Repository for fact_evidence_bindings table."""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import FactEvidenceBindingModel


class FactEvidenceBindingRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        fact_id: str,
        subject_iri: str,
        predicate_iri: str,
        object_value: str,
        graph_iri: str,
        text: str,
        chunk_id: str | None = None,
        evidence_artifact_id: str | None = None,
        document_filename: str | None = None,
        sequence: int | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        actor: str | None = None,
        reason: str | None = None,
    ) -> FactEvidenceBindingModel:
        binding = FactEvidenceBindingModel(
            id=str(uuid4()),
            fact_id=fact_id,
            subject_iri=subject_iri,
            predicate_iri=predicate_iri,
            object_value=object_value,
            graph_iri=graph_iri,
            text=text,
            chunk_id=chunk_id,
            evidence_artifact_id=evidence_artifact_id,
            document_filename=document_filename,
            sequence=sequence,
            char_start=char_start,
            char_end=char_end,
            actor=actor,
            reason=reason,
        )
        self.session.add(binding)
        self.session.flush()
        return binding

    def delete(self, binding_id: str) -> bool:
        binding = self.session.get(FactEvidenceBindingModel, binding_id)
        if binding is None:
            return False
        self.session.delete(binding)
        self.session.flush()
        return True

    def list_by_fact_id(self, fact_id: str) -> list[FactEvidenceBindingModel]:
        stmt = select(FactEvidenceBindingModel).where(
            FactEvidenceBindingModel.fact_id == fact_id
        ).order_by(FactEvidenceBindingModel.created_at)
        return list(self.session.scalars(stmt))

    def list_by_fact_ids(self, fact_ids: list[str]) -> dict[str, list[FactEvidenceBindingModel]]:
        if not fact_ids:
            return {}
        stmt = select(FactEvidenceBindingModel).where(
            FactEvidenceBindingModel.fact_id.in_(fact_ids)
        ).order_by(FactEvidenceBindingModel.created_at)
        result: dict[str, list[FactEvidenceBindingModel]] = {}
        for binding in self.session.scalars(stmt):
            result.setdefault(binding.fact_id, []).append(binding)
        return result

    def count_facts_with_bindings(self, fact_ids: list[str]) -> set[str]:
        """Return subset of fact_ids that have at least one binding."""
        if not fact_ids:
            return set()
        stmt = select(FactEvidenceBindingModel.fact_id).where(
            FactEvidenceBindingModel.fact_id.in_(fact_ids)
        ).distinct()
        return set(self.session.scalars(stmt))
```

- [ ] **Step 4: Verify conftest provides `db_session` fixture**

Run: `cd backend && grep -n "db_session" tests/conftest.py`
If missing, add fixture to `tests/conftest.py`:
```python
@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/test_fact_evidence_repository.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories/fact_evidence_repository.py backend/tests/test_fact_evidence_repository.py backend/tests/conftest.py
git commit -m "feat(repos): add FactEvidenceBindingRepository"
```

---

## Phase 2: New Write Path (Tasks 4-7)

### Task 4: Add `compile_bind_fact_evidence` command

**Files:**
- Modify: `backend/app/services/semantic_command_compiler.py`
- Create: `backend/tests/test_compile_bind_fact_evidence.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_compile_bind_fact_evidence.py
import pytest

from app.services.semantic_command_compiler import (
    compile_bind_fact_evidence,
    compile_unbind_fact_evidence,
)
from app.services.fact_id import compute_fact_id, canonical_object_term


def test_bind_fact_evidence_with_text_only(ns_factory):
    ns = ns_factory()
    payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "42",
        "object_is_iri": False,
        "graph_iri": "http://example/g",
        "text": "evidence snippet",
        "actor": "user:alice",
    }
    cmd = compile_bind_fact_evidence(payload, ns, settings=None)
    assert cmd.command_kind == "bind_fact_evidence"
    assert cmd.object_kind == "fact_evidence"
    expected_fid = compute_fact_id(
        "http://example/s", "http://example/p",
        canonical_object_term("42", is_iri=False), "http://example/g"
    )
    assert cmd.metadata["fact_id"] == expected_fid
    assert cmd.metadata["text"] == "evidence snippet"
    # No RDF delta — evidence lives in PG only
    assert cmd.delta.inserts == []
    assert cmd.delta.deletes == []


def test_bind_fact_evidence_rejects_fact_id_mismatch(ns_factory):
    ns = ns_factory()
    payload = {
        "ontology_id": "ont-1",
        "fact_id": "0" * 64,  # wrong
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "42",
        "object_is_iri": False,
        "graph_iri": "http://example/g",
        "text": "t",
    }
    with pytest.raises(Exception, match="fact_id mismatch"):
        compile_bind_fact_evidence(payload, ns, settings=None)
```

Add the `ns_factory` fixture to `tests/conftest.py` if not already present (return a `SemanticNamespace` mock with `.vocab`, `.base_iri`, `.resource()`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_compile_bind_fact_evidence.py -v`
Expected: FAIL `ImportError: cannot import name 'compile_bind_fact_evidence'`

- [ ] **Step 3: Write implementation**

Add to `backend/app/services/semantic_command_compiler.py` (near other compile_ functions):

```python
def compile_bind_fact_evidence(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Bind evidence text or chunk to a specific fact (identified by fact_id).

    Stores in Postgres only — does not write RDF. The fact_id is computed
    from (s, p, o, g) using canonical N-Triples; if the caller provides a
    fact_id it must match or the command is rejected.
    """
    ontology_id = _required(payload, "ontology_id")
    subject_iri = _required(payload, "subject_iri")
    predicate_iri = _required(payload, "predicate_iri")
    object_value = _required(payload, "object_value")
    object_is_iri = bool(payload.get("object_is_iri", False))
    object_datatype = payload.get("object_datatype")
    graph_iri = payload.get("graph_iri") or _data_graph_iri(ns, ontology_id)
    text = str(_required(payload, "text")).strip()
    if not text:
        raise InvalidCommandPayload("text must not be empty")

    object_term = canonical_object_term(
        object_value, is_iri=object_is_iri, datatype=object_datatype
    )
    fid = compute_fact_id(subject_iri, predicate_iri, object_term, graph_iri)

    provided_fid = payload.get("fact_id")
    if provided_fid is not None and provided_fid != fid:
        raise InvalidCommandPayload(
            f"fact_id mismatch: caller provided {provided_fid}, computed {fid}"
        )

    # No RDF writes — repository call is performed by the command executor
    # (SemanticCommandExecutor / compile_and_apply pipeline) at apply time,
    # not here. The delta is empty.
    delta = RdfGraphDelta(inserts=[], deletes=[])
    return CompiledCommand(
        command_kind="bind_fact_evidence",
        delta=delta,
        object_kind="fact_evidence",
        source_ids=[subject_iri, fid],
        target_graph_iris=[],  # no graph writes
        metadata={
            "ontology_id": ontology_id,
            "fact_id": fid,
            "subject_iri": subject_iri,
            "predicate_iri": predicate_iri,
            "object_value": object_term,
            "graph_iri": graph_iri,
            "chunk_id": payload.get("chunk_id"),
            "evidence_artifact_id": payload.get("evidence_artifact_id"),
            "document_filename": payload.get("document_filename"),
            "sequence": payload.get("sequence"),
            "char_start": payload.get("char_start"),
            "char_end": payload.get("char_end"),
            "text": text,
            "actor": payload.get("actor"),
            "reason": payload.get("reason"),
        },
    )
```

Add imports at top of file:
```python
from app.services.fact_id import canonical_object_term, compute_fact_id
```

- [ ] **Step 4: Run test**

Run: `cd backend && uv run pytest tests/test_compile_bind_fact_evidence.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_command_compiler.py backend/tests/test_compile_bind_fact_evidence.py backend/tests/conftest.py
git commit -m "feat(cmd): add compile_bind_fact_evidence"
```

---

### Task 5: Add `compile_unbind_fact_evidence` command

**Files:**
- Modify: `backend/app/services/semantic_command_compiler.py`
- Modify: `backend/tests/test_compile_bind_fact_evidence.py` (append test)

- [ ] **Step 1: Write failing test**

Append to `tests/test_compile_bind_fact_evidence.py`:

```python
def test_unbind_fact_evidence_by_binding_id(ns_factory):
    ns = ns_factory()
    payload = {
        "ontology_id": "ont-1",
        "binding_id": "abc-123",
    }
    cmd = compile_unbind_fact_evidence(payload, ns, settings=None)
    assert cmd.command_kind == "unbind_fact_evidence"
    assert cmd.metadata["binding_id"] == "abc-123"
    assert cmd.delta.inserts == []
    assert cmd.delta.deletes == []


def test_unbind_fact_evidence_requires_binding_id(ns_factory):
    ns = ns_factory()
    with pytest.raises(Exception):
        compile_unbind_fact_evidence({"ontology_id": "ont-1"}, ns, settings=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_compile_bind_fact_evidence.py::test_unbind_fact_evidence_by_binding_id -v`
Expected: FAIL `ImportError`

- [ ] **Step 3: Write implementation**

```python
def compile_unbind_fact_evidence(
    payload: dict[str, Any], ns: SemanticNamespace, settings: Settings
) -> CompiledCommand:
    """Delete a fact evidence binding from Postgres by binding_id."""
    _required(payload, "ontology_id")
    binding_id = _required(payload, "binding_id")
    delta = RdfGraphDelta(inserts=[], deletes=[])
    return CompiledCommand(
        command_kind="unbind_fact_evidence",
        delta=delta,
        object_kind="fact_evidence",
        source_ids=[binding_id],
        target_graph_iris=[],
        metadata={"ontology_id": payload["ontology_id"], "binding_id": binding_id},
    )
```

- [ ] **Step 4: Run test**

Run: `cd backend && uv run pytest tests/test_compile_bind_fact_evidence.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_command_compiler.py backend/tests/test_compile_bind_fact_evidence.py
git commit -m "feat(cmd): add compile_unbind_fact_evidence"
```

---

### Task 6: Register new commands in `_COMPILERS`

**Files:**
- Modify: `backend/app/services/semantic_command_compiler.py` (the `_COMPILERS` dict near L1606)

- [ ] **Step 1: Add registration**

Find the `_COMPILERS = {...}` dict and add:

```python
"bind_fact_evidence": compile_bind_fact_evidence,
"unbind_fact_evidence": compile_unbind_fact_evidence,
```

- [ ] **Step 2: Verify via Python**

Run: `cd backend && uv run python -c "from app.services.semantic_command_compiler import _COMPILERS; assert 'bind_fact_evidence' in _COMPILERS; assert 'unbind_fact_evidence' in _COMPILERS; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/semantic_command_compiler.py
git commit -m "feat(cmd): register bind/unbind_fact_evidence compilers"
```

---

### Task 7: Wire command executor to PG repository + add REST endpoints

**Files:**
- Modify: `backend/app/services/semantic.py` (or wherever `compile_and_apply` lives — find via grep)
- Create: `backend/app/api/fact_evidence.py`
- Modify: `backend/app/api/__init__.py` or wherever routers are registered
- Create: `backend/tests/test_fact_evidence_api.py`

- [ ] **Step 1: Locate the command executor**

Run: `cd backend && grep -rn "compile_and_apply\|class SemanticCommandExecutor" app/services/ | head -10`
Identify the file that applies compiled commands. Call this `<executor_file>`.

- [ ] **Step 2: Wire PG writes in the executor**

In `<executor_file>`, modify the apply path so that when `compiled.command_kind in {"bind_fact_evidence", "unbind_fact_evidence"}`, it calls `FactEvidenceBindingRepository(session)` instead of (or in addition to) the RDF store.

Sketch (adapt to actual executor class structure):

```python
# Pseudocode for the apply step
if compiled.command_kind == "bind_fact_evidence":
    repo = FactEvidenceBindingRepository(session)
    repo.create(
        fact_id=compiled.metadata["fact_id"],
        subject_iri=compiled.metadata["subject_iri"],
        predicate_iri=compiled.metadata["predicate_iri"],
        object_value=compiled.metadata["object_value"],
        graph_iri=compiled.metadata["graph_iri"],
        text=compiled.metadata["text"],
        chunk_id=compiled.metadata.get("chunk_id"),
        evidence_artifact_id=compiled.metadata.get("evidence_artifact_id"),
        document_filename=compiled.metadata.get("document_filename"),
        sequence=compiled.metadata.get("sequence"),
        char_start=compiled.metadata.get("char_start"),
        char_end=compiled.metadata.get("char_end"),
        actor=compiled.metadata.get("actor"),
        reason=compiled.metadata.get("reason"),
    )
    return compiled_result_no_rdf_delta
elif compiled.command_kind == "unbind_fact_evidence":
    repo = FactEvidenceBindingRepository(session)
    repo.delete(compiled.metadata["binding_id"])
    return compiled_result_no_rdf_delta
```

- [ ] **Step 3: Write API test**

```python
# backend/tests/test_fact_evidence_api.py
def test_post_fact_evidence_creates_binding(client, graph_set_factory, db_session):
    gs = graph_set_factory()
    payload = {
        "ontology_id": gs.ontology_id,
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "42",
        "object_is_iri": False,
        "graph_iri": "http://example/g",
        "text": "evidence snippet",
        "actor": "user:alice",
    }
    resp = client.post(f"/api/semantic/graph-sets/{gs.id}/fact-evidence", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["fact_id"]
    assert body["text"] == "evidence snippet"


def test_delete_fact_evidence(client, graph_set_factory, db_session):
    gs = graph_set_factory()
    # Create first
    create = client.post(f"/api/semantic/graph-sets/{gs.id}/fact-evidence", json={...}).json()
    binding_id = create["id"]
    resp = client.delete(f"/api/semantic/graph-sets/{gs.id}/fact-evidence/{binding_id}")
    assert resp.status_code == 204


def test_get_missing_evidence_facts(client, graph_set_factory, db_session):
    gs = graph_set_factory()
    resp = client.get(f"/api/semantic/graph-sets/{gs.id}/missing-evidence-facts?limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body
    assert "fact_ids" in body
```

(Adapt `graph_set_factory` to whatever the project test fixtures already provide; check `tests/conftest.py` and existing semantic API tests for patterns.)

- [ ] **Step 4: Run API test to verify it fails**

Run: `cd backend && uv run pytest tests/test_fact_evidence_api.py -v`
Expected: FAIL with 404

- [ ] **Step 5: Implement API router**

```python
# backend/app/api/fact_evidence.py
"""REST endpoints for fact-level evidence bindings."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_request_context
from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
from app.services.fact_id import canonical_object_term, compute_fact_id
from app.services.semantic_command_compiler import compile_bind_fact_evidence, compile_unbind_fact_evidence

router = APIRouter(tags=["semantic"])


class BindFactEvidenceRequest(BaseModel):
    ontology_id: str
    subject_iri: str
    predicate_iri: str
    object_value: str
    object_is_iri: bool = False
    object_datatype: str | None = None
    graph_iri: str | None = None
    fact_id: str | None = None
    chunk_id: str | None = None
    evidence_artifact_id: str | None = None
    document_filename: str | None = None
    sequence: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    text: str
    actor: str | None = None
    reason: str | None = None


@router.post("/api/semantic/graph-sets/{graph_set_id}/fact-evidence")
def create_fact_evidence(
    graph_set_id: str,
    payload: BindFactEvidenceRequest,
    request=Depends(get_request_context),
    session: Session = Depends(get_db),
):
    cmd = compile_bind_fact_evidence(payload.model_dump(), ns=request.ns, settings=request.settings)
    # Apply directly (the command has no RDF delta)
    repo = FactEvidenceBindingRepository(session)
    binding = repo.create(
        fact_id=cmd.metadata["fact_id"],
        subject_iri=cmd.metadata["subject_iri"],
        predicate_iri=cmd.metadata["predicate_iri"],
        object_value=cmd.metadata["object_value"],
        graph_iri=cmd.metadata["graph_iri"],
        text=cmd.metadata["text"],
        chunk_id=cmd.metadata.get("chunk_id"),
        evidence_artifact_id=cmd.metadata.get("evidence_artifact_id"),
        document_filename=cmd.metadata.get("document_filename"),
        sequence=cmd.metadata.get("sequence"),
        char_start=cmd.metadata.get("char_start"),
        char_end=cmd.metadata.get("char_end"),
        actor=cmd.metadata.get("actor"),
        reason=cmd.metadata.get("reason"),
    )
    session.commit()
    return {
        "id": binding.id,
        "fact_id": binding.fact_id,
        "text": binding.text,
        "chunk_id": binding.chunk_id,
        "created_at": binding.created_at.isoformat(),
    }


@router.delete("/api/semantic/graph-sets/{graph_set_id}/fact-evidence/{binding_id}")
def delete_fact_evidence(
    graph_set_id: str,
    binding_id: str,
    session: Session = Depends(get_db),
):
    repo = FactEvidenceBindingRepository(session)
    if not repo.delete(binding_id):
        raise HTTPException(status_code=404, detail="binding not found")
    session.commit()
    return None  # 204


@router.get("/api/semantic/graph-sets/{graph_set_id}/missing-evidence-facts")
def list_missing_evidence_facts(
    graph_set_id: str,
    limit: int = 500,
    session: Session = Depends(get_db),
    request=Depends(get_request_context),
):
    """Return fact_ids in this graph_set that have zero evidence bindings."""
    # 1. Get all asserted fact_ids from RDF (use read-model service)
    from app.services.semantic_read_model import SemanticReadModelService
    svc = SemanticReadModelService(... )  # adapt to project wiring
    all_facts = svc.list_fact_ids(graph_set_id, limit=limit)
    # 2. Subtract those with bindings
    repo = FactEvidenceBindingRepository(session)
    with_bindings = repo.count_facts_with_bindings(all_facts)
    missing = [fid for fid in all_facts if fid not in with_bindings]
    return {"count": len(missing), "fact_ids": missing}
```

Register router in `backend/app/api/__init__.py` (or wherever FastAPI app is assembled — grep `include_router`).

- [ ] **Step 6: Run API tests**

Run: `cd backend && uv run pytest tests/test_fact_evidence_api.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/fact_evidence.py backend/app/api/__init__.py backend/tests/test_fact_evidence_api.py <executor_file>
git commit -m "feat(api): add fact-evidence REST endpoints + executor wiring"
```

---

## Phase 3: New Read Path (Tasks 8-10)

### Task 8: Add `_fetch_evidence_bindings_from_pg` to read model service

**Files:**
- Modify: `backend/app/services/semantic_read_model.py`

- [ ] **Step 1: Locate where `_attach_evidence_bindings` is called**

Run: `cd backend && grep -n "_attach_evidence_bindings\|evidence_bindings" app/services/semantic_read_model.py`
Likely call sites: L1018, L1055, L1090.

- [ ] **Step 2: Add new PG-based fetch method**

Add a new method to `SemanticReadModelService`:

```python
def _fetch_evidence_bindings_from_pg(
    self, fact_ids: list[str], session: Session
) -> dict[str, list[dict[str, Any]]]:
    """Batch-fetch evidence bindings from Postgres, bucketed by fact_id."""
    if not fact_ids:
        return {}
    repo = FactEvidenceBindingRepository(session)
    raw = repo.list_by_fact_ids(fact_ids)
    return {
        fid: [
            {
                "id": b.id,
                "fact_id": b.fact_id,
                "chunk_id": b.chunk_id,
                "evidence_artifact_id": b.evidence_artifact_id,
                "document_filename": b.document_filename,
                "sequence": b.sequence,
                "char_start": b.char_start,
                "char_end": b.char_end,
                "text_preview": (b.text[:200] + "..." if len(b.text) > 200 else b.text),
                "text": b.text,
                "actor": b.actor,
                "reason": b.reason,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bindings
        ]
        for fid, bindings in raw.items()
    }
```

Add imports:
```python
from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
```

The `session` parameter comes from the request scope. Trace how the service currently obtains a SQLAlchemy session (probably via DI in `api/semantic.py`) and adapt.

- [ ] **Step 3: Smoke test**

Run: `cd backend && uv run python -c "from app.services.semantic_read_model import SemanticReadModelService; print(hasattr(SemanticReadModelService, '_fetch_evidence_bindings_from_pg'))"`
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/semantic_read_model.py
git commit -m "feat(read): add PG-based evidence_bindings fetch"
```

---

### Task 9: Refactor `_decorate_fact_row` to derive `evidence_status`

**Files:**
- Modify: `backend/app/services/semantic_read_model.py` (`_decorate_fact_row` L1115-1186)

- [ ] **Step 1: Change `_decorate_fact_row` to derive evidence_status from PG**

Modify so it accepts a pre-fetched `bindings_count_by_fact: dict[str, int]` parameter (or an already-decorated `bindings_by_fact: dict[str, list]`):

```python
def _decorate_fact_row(
    self,
    row: dict[str, Any],
    *,
    assertion_kind: str,
    scope: ScopeResolution,
    bindings_by_fact: dict[str, list[dict[str, Any]]] | None = None,
    derived_run_id: str | None = None,
    stale: bool | None = None,
    stale_reason: str | None = None,
) -> dict[str, Any]:
    """Decorate a raw SPARQL row into the unified FactRow shape."""
    subject_iri = self._cell(row, "subject") or ""
    subject_label = self._cell(row, "subject_label")
    predicate_iri = self._cell(row, "predicate") or ""
    predicate_label = self._cell(row, "predicate_label")
    object_value: Any = self._cell(row, "object")
    object_is_iri = self._cell_is_uri(row, "object")
    object_label = self._cell(row, "object_label")
    source_graph_iri = self._cell(row, "graph") or (
        scope.source_graph_iris[0] if scope.source_graph_iris else ""
    )

    audit_status = self._cell(row, "audit_status") or "pending"
    fact_id = self._fact_id(subject_iri, predicate_iri, object_value or "", source_graph_iri)

    # Derive evidence_status from PG bindings
    bindings = (bindings_by_fact or {}).get(fact_id, [])
    evidence_status = "with_evidence" if bindings else "missing_evidence"

    # ... rest of the function unchanged (stale_flag, fact_id hash, item dict) ...
    item: dict[str, Any] = {
        "id": fact_id,
        "fact_id": fact_id,
        "assertion_kind": assertion_kind,
        "subject_iri": subject_iri,
        "subject_label": subject_label,
        "predicate_iri": predicate_iri,
        "predicate_label": predicate_label,
        "object_value": object_value,
        "object_is_iri": object_is_iri,
        "object_label": object_label,
        "graph_iri": source_graph_iri,
        "source_graph_iri": source_graph_iri,
        "evidence_status": evidence_status,
        "evidence_bindings": bindings,
        "audit_status": audit_status,
        "stale": stale_bool,
        "stale_reason": stale_reason_val,
    }
    if derived_run_id is not None:
        item["derived_from"] = {"run_id": derived_run_id}
    return item
```

Note: `_fact_id` here is still the read-side 4-tuple version (L1189); it will be replaced by `compute_fact_id` from new util in Task 11.

- [ ] **Step 2: Update callers**

In `_compose_fact_audit_queue` (L990-1090), where `_decorate_fact_row` is called, you must first collect all fact_ids, batch-query PG, then pass `bindings_by_fact`:

```python
# After fetching SPARQL rows but before decorating:
items = [self._decorate_fact_row(row, assertion_kind=kind, scope=scope) for row in rows]
fact_ids = [it["fact_id"] for it in items]
bindings_by_fact = self._fetch_evidence_bindings_from_pg(fact_ids, session)
for it in items:
    fid = it["fact_id"]
    it["evidence_bindings"] = bindings_by_fact.get(fid, [])
    it["evidence_status"] = "with_evidence" if it["evidence_bindings"] else "missing_evidence"
```

(Or fold the bindings parameter into `_decorate_fact_row` as shown in Step 1.)

- [ ] **Step 3: Run read model tests**

Run: `cd backend && uv run pytest tests/test_semantic_read_model.py -v -k "fact_audit or decorate"`
Expected: Many will fail because they assert old RDF-based behavior. **Note failing tests** for Task 28 to rewrite.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/semantic_read_model.py
git commit -m "refactor(read): derive evidence_status from PG bindings"
```

---

### Task 10: Switch `_missing_evidence_count` and missing-evidence tab to PG

**Files:**
- Modify: `backend/app/services/semantic_read_model.py` (`_missing_evidence_count` L529-549, `_compose_fact_audit_queue` L990-1019 for missing_evidence kind)

- [ ] **Step 1: Replace `_missing_evidence_count` with PG count**

```python
def _missing_evidence_count(self, scope: ScopeResolution, session: Session) -> int:
    """Count facts in scope with zero evidence bindings in PG."""
    # 1. Get all asserted fact_ids via SPARQL (lightweight)
    fact_ids = self._list_asserted_fact_ids(scope)
    if not fact_ids:
        return 0
    # 2. Subtract those with at least one binding
    repo = FactEvidenceBindingRepository(session)
    with_bindings = repo.count_facts_with_bindings(fact_ids)
    return len(fact_ids) - len(with_bindings)
```

Add a helper `_list_asserted_fact_ids(scope) -> list[str]` that runs a lightweight SPARQL `SELECT DISTINCT ?s ?p ?o ?g WHERE { ... }` and projects to fact_ids.

- [ ] **Step 2: Update `_compose_fact_audit_queue` for `kind=missing_evidence`**

```python
if resolved_kind == "missing_evidence":
    # Get all asserted fact_ids, subtract those with bindings
    all_fact_ids = self._list_asserted_fact_ids(scope)
    repo = FactEvidenceBindingRepository(session)
    with_bindings = repo.count_facts_with_bindings(all_fact_ids)
    missing_ids = set(all_fact_ids) - with_bindings
    # Re-query SPARQL only for facts in missing_ids (or filter client-side)
    # See Task 11 for unified _fact_id; here we still use read-side hash
    items = [it for it in items if it["fact_id"] in missing_ids]
else:
    # asserted / inferred / rule_derived: decorate normally
    pass
```

- [ ] **Step 3: Run tests**

Run: `cd backend && uv run pytest tests/test_semantic_read_model.py -v -k "missing"`
Expected: FAIL (will be rewritten in Task 28). Note specific failures.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/semantic_read_model.py
git commit -m "refactor(read): missing_evidence count + tab query PG"
```

---

## Phase 4: Delete Legacy Write Path (Tasks 11-13)

### Task 11: Delete 4 legacy commands + `_fact_id_for` + `_canonical_ntriples`

**Files:**
- Modify: `backend/app/services/semantic_command_compiler.py`

- [ ] **Step 1: Delete the following functions and registrations**

Remove these functions:
- `compile_submit_assertion` (L240-286)
- `compile_update_evidence_status` (L289-320)
- `compile_bind_fact_evidence_text` (L399-443)
- `compile_unbind_fact_evidence` (L446-476)  ← the OLD one; new one with same name is added in Task 5
- `_fact_id_for` (L1468-1473)
- `_canonical_ntriples` (L1458-1466)

Remove from `_COMPILERS` dict (L1606-1611):
- `"submit_assertion"`
- `"update_evidence_status"`
- `"bind_fact_evidence_text"` (the old registration — do NOT remove the new `bind_fact_evidence` / `unbind_fact_evidence` added in Task 6)
- `"unbind_fact_evidence"` (the old one) — verify you only delete this if it's still pointing to old function. If Task 6's registration overwrote it, skip.

- [ ] **Step 2: Update callers of `_fact_id_for`**

Find all callers: Run `cd backend && grep -n "_fact_id_for\|_canonical_ntriples" app/services/semantic_command_compiler.py`

Replace with calls to `compute_fact_id` from new util. Callers are at L343 (update_fact), L376 (delete_fact), L1549/1568/1585/1591 (review_assertion). For each, you need:
- The object term in N-Triples format (use `canonical_object_term`)
- The graph_iri

For example, in `compile_delete_fact` (around L370-391):
```python
# Before:
fact_id = _fact_id_for(subject_iri, predicate_iri, obj)
# After:
graph_iri = payload.get("graph_iri") or _data_graph_iri(ns, ontology_id)
object_ntriples = obj  # obj is already in N-Triples form from _object_term()
fact_id = compute_fact_id(subject_iri, predicate_iri, object_ntriples, graph_iri)
```

Add at top of file:
```python
from app.services.fact_id import compute_fact_id, canonical_object_term
```

- [ ] **Step 3: Verify backend imports**

Run: `cd backend && uv run python -c "from app.services.semantic_command_compiler import _COMPILERS; print(sorted(_COMPILERS.keys()))"`
Expected: No `submit_assertion`, `update_evidence_status`, `bind_fact_evidence_text`. Has `bind_fact_evidence`, `unbind_fact_evidence`.

- [ ] **Step 4: Run all command-compiler tests**

Run: `cd backend && uv run pytest tests/test_semantic_command_compiler_stage2.py -v`
Expected: Some tests fail (asserting old behavior). Note for Task 28.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_command_compiler.py
git commit -m "refactor(cmd): delete legacy submit_assertion/update_evidence_status/bind_fact_evidence_text + unify fact_id"
```

---

### Task 12: Remove default missing_evidence markers from create_entity / create_relation

**Files:**
- Modify: `backend/app/services/semantic_command_compiler.py` (L1000-1004 create_entity, L1140-1145 create_relation)

- [ ] **Step 1: Remove the op:evidenceStatus write**

In `compile_create_entity` (around L1000-1004), delete:
```python
# Default evidence_status marker.
insert_quads.append(
    (f"<{entity_iri}>", f"<{op}evidenceStatus>",
     _literal_term("missing_evidence"), graph_iri)
)
```

In `compile_create_relation` (around L1140-1145), delete the equivalent block.

- [ ] **Step 2: Verify no other writes of op:evidenceStatus**

Run: `cd backend && grep -n 'evidenceStatus\|"missing_evidence"' app/services/semantic_command_compiler.py`
Expected: No matches (or only inside string literals for tests).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/semantic_command_compiler.py
git commit -m "refactor(cmd): create_entity/relation no longer write op:evidenceStatus"
```

---

### Task 13: Modify `semantic_migration.py` fact_claim branch to skip

**Files:**
- Modify: `backend/app/services/semantic_migration.py` (L685-695)

- [ ] **Step 1: Inspect current code**

Run: `cd backend && sed -n '680,700p' app/services/semantic_migration.py`

- [ ] **Step 2: Replace submit_assertion dispatch with skip + log**

```python
# Around L685-695 — replace the if object_kind == "fact_claim" branch:
if object_kind == "fact_claim":
    logger.warning(
        "Skipping legacy fact_claim migration row (id=%s): the submit_assertion "
        "command and op:FactClaim model have been removed. Re-bind evidence via "
        "the new fact_evidence_bindings API after migration.",
        row.get("id"),
    )
    continue  # skip this row, do not write to RDF
```

If the broader code expects a `command_kind` for every row, leave fact_claim out of the dispatch entirely (only handle other object_kinds).

- [ ] **Step 3: Run migration tests**

Run: `cd backend && uv run pytest tests/test_semantic_migration_service.py -v`
Expected: FAIL on tests that assert submit_assertion was called. Note for Task 28.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/semantic_migration.py
git commit -m "refactor(migration): skip legacy fact_claim rows instead of writing submit_assertion"
```

---

## Phase 5: Delete Legacy Read Path (Tasks 14-16)

### Task 14: Delete `_attach_evidence_bindings` / `_EVIDENCE_BINDING_SPARQL` / `_fetch_evidence_bindings`

**Files:**
- Modify: `backend/app/services/semantic_read_model.py` (L1412-1500+)

- [ ] **Step 1: Delete the three methods/attrs**

Remove:
- `_attach_evidence_bindings` (L1412-1445)
- `_EVIDENCE_BINDING_SPARQL` class attr (L1447-1461)
- `_fetch_evidence_bindings` (L1463-1500+)

- [ ] **Step 2: Verify no remaining callers**

Run: `cd backend && grep -n "_attach_evidence_bindings\|_EVIDENCE_BINDING_SPARQL\|_fetch_evidence_bindings" app/`
Expected: No matches (callers in L1018/1055/1090 should have been updated in Task 9).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/semantic_read_model.py
git commit -m "refactor(read): delete RDF-based evidence_bindings fetchers"
```

---

### Task 15: Delete `missing-evidence-list` SPARQL template

**Files:**
- Modify: `backend/app/services/semantic_sparql_templates.py` (L444-479)

- [ ] **Step 1: Remove the template entry**

Delete the `"missing-evidence-list": ReadModelTemplate(...)` block entirely.

- [ ] **Step 2: Remove `"missing_evidence"` from `_FACT_KINDS`**

In `backend/app/services/semantic_read_model.py` (L956):
```python
# Before:
_FACT_KINDS = ("asserted", "inferred", "rule_derived", "missing_evidence")
# After:
_FACT_KINDS = ("asserted", "inferred", "rule_derived")
```

But the `kind=missing_evidence` query parameter still needs to work (now PG-driven, see Task 10) — keep the kind parameter validation accepting it but route it to the PG-driven path. Add a comment explaining the special handling.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/semantic_sparql_templates.py backend/app/services/semantic_read_model.py
git commit -m "refactor(templates): drop missing-evidence-list SPARQL template"
```

---

### Task 16: Clean `op:evidenceStatus` projections from SPARQL templates

**Files:**
- Modify: `backend/app/services/semantic_sparql_templates.py`
- Modify: `backend/app/services/semantic_read_model.py` (only the `_cell(row, "evidence_status")` call sites)

- [ ] **Step 1: Inventory all references**

Run: `cd backend && grep -n 'op:evidenceStatus\|evidence_status' app/services/semantic_sparql_templates.py`

For each match, decide: delete the line if it's an `OPTIONAL { ?s op:evidenceStatus ... }` or `FILTER(?predicate != op:evidenceStatus)` clause, or remove `evidence_status` from the SELECT list.

- [ ] **Step 2: Edit each template**

Specifically:
- L123: remove `GRAPH ?g { ?s op:evidenceStatus "missing_evidence" . }` from the staleness query
- L286, L437: remove `OPTIONAL { ?entity/?subject op:evidenceStatus ?evidence_status . }`
- L406-442 (fact-audit-queue): remove `?evidence_status` from SELECT, remove the OPTIONAL clause
- L468, L471: gone (deleted in Task 15)

For each `ReadModelTemplate(...)` constructor call, also remove the `evidence_status="..."` kwarg (search for `evidence_status=` in the same file).

- [ ] **Step 3: Remove `_cell(row, "evidence_status")` references in read_model.py**

Run: `cd backend && grep -n '_cell(row, "evidence_status")' app/services/semantic_read_model.py`
Delete those lines (they should already be unused after Task 9).

- [ ] **Step 4: Verify**

Run: `cd backend && grep -n "evidenceStatus\|evidence_status" app/services/semantic_sparql_templates.py app/services/semantic_read_model.py | grep -v "missing_evidence_dependencies\|_fetch_evidence_bindings_from_pg"`
Expected: minimal or no matches (only field-name strings, no RDF predicate references).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_sparql_templates.py backend/app/services/semantic_read_model.py
git commit -m "refactor(templates): purge op:evidenceStatus from all SPARQL templates"
```

---

## Phase 6: Clean Service Layer (Tasks 17-20)

### Task 17: Delete `semantic_missing_evidence.py`

**Files:**
- Delete: `backend/app/services/semantic_missing_evidence.py`
- Modify: every file that imports from it

- [ ] **Step 1: Find all importers**

Run: `cd backend && grep -rn "semantic_missing_evidence\|SemanticMissingEvidenceService\|DERIVED_FROM_MISSING_EVIDENCE" app/`

- [ ] **Step 2: Delete the file**

```bash
rm backend/app/services/semantic_missing_evidence.py
```

- [ ] **Step 3: For each importer, remove the import and any usage**

Likely importers (per spec):
- `semantic.py` (factory function)
- `semantic_reasoning.py`
- `semantic_validation.py`
- `semantic_rule_execution.py`
- `api/semantic.py`

Remove `_missing_evidence_service` factory in `semantic.py`. Remove import + DI in the three service files. For any code path that called `.scan_for_missing_evidence()` or `.annotate_generated_statement()`, delete the call entirely (do not replace with anything — the new design has no equivalent because missing is derived).

- [ ] **Step 4: Verify imports**

Run: `cd backend && uv run python -c "import app.services.semantic; import app.services.semantic_reasoning; import app.services.semantic_validation; import app.services.semantic_rule_execution; import app.api.semantic; print('OK')"`
Expected: `OK` (no import errors).

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/services/semantic_missing_evidence.py backend/app/services/semantic.py backend/app/services/semantic_reasoning.py backend/app/services/semantic_validation.py backend/app/services/semantic_rule_execution.py backend/app/api/semantic.py
git commit -m "refactor: delete SemanticMissingEvidenceService and all usages"
```

---

### Task 18: Clean reasoning + validation services

**Files:**
- Modify: `backend/app/services/semantic_reasoning.py`
- Modify: `backend/app/services/semantic_validation.py`

- [ ] **Step 1: Remove all `missing_evidence_*` references**

In each file:
- Remove `SemanticMissingEvidenceService` from constructor args / DI
- Remove `missing_evidence_dependencies` from response schemas (or set field to default `None` / `{}` if removing breaks API contract — prefer removing)
- Remove any `result["missing_evidence_dependencies"] = ...` writes

- [ ] **Step 2: Run service tests**

Run: `cd backend && uv run pytest tests/test_semantic_reasoning.py tests/test_semantic_validation.py -v`
Expected: FAIL on tests asserting `missing_evidence_dependencies`. Note for Task 28.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/semantic_reasoning.py backend/app/services/semantic_validation.py
git commit -m "refactor(reasoning/validation): drop missing_evidence_dependencies"
```

---

### Task 19: Clean `semantic_rule_execution.py` (remove derived_from_missing_evidence writes)

**Files:**
- Modify: `backend/app/services/semantic_rule_execution.py`

- [ ] **Step 1: Remove RDF writes of derived_from_missing_evidence**

Find around L660-665:
```python
# Delete something like:
insert_quads.append(
    (f"<{fact_iri}>", f"<{op}evidenceStatus>",
     _literal_term("derived_from_missing_evidence"), graph_iri)
)
```

Also remove all references in L39, 70-79, 153-159, 171, 190, 244-282, 301, 379-422, 462-483, 601-665, 799-843.

- [ ] **Step 2: Remove from response schemas**

If the rule execution response includes `missing_evidence_dependencies` or `derived_from_missing_evidence`, remove or default to empty.

- [ ] **Step 3: Run rule tests**

Run: `cd backend && uv run pytest tests/test_semantic_rule_execution.py -v` (if exists)
Expected: FAIL or PASS depending on test coverage. Note for Task 28.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/semantic_rule_execution.py
git commit -m "refactor(rule_exec): remove derived_from_missing_evidence RDF writes"
```

---

### Task 20: Modify `build_overview` (PG count) + delete `semantic.py` protections

**Files:**
- Modify: `backend/app/services/semantic_build_overview.py`
- Modify: `backend/app/services/semantic.py`

- [ ] **Step 1: Replace `missing_evidence_count` in build_overview**

In `semantic_build_overview.py` (L24, L97, L133-137), change `missing_evidence_count` to call the new PG-driven `_missing_evidence_count(scope, session)` from `SemanticReadModelService`. Add a guard so the field is omitted if no session is available.

- [ ] **Step 2: Delete `_missing_evidence_write_warnings` / `_missing_evidence_read_warnings`**

In `backend/app/services/semantic.py` (L752-793), delete both functions and all callers.

- [ ] **Step 3: Verify**

Run: `cd backend && uv run python -c "import app.services.semantic; import app.services.semantic_build_overview; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/semantic_build_overview.py backend/app/services/semantic.py
git commit -m "refactor: missing_evidence_count via PG; remove write/read warning gates"
```

---

## Phase 7: Clean API + MCP (Tasks 21-22)

### Task 21: Delete `/missing-evidence` route + MCP tool + schemas cleanup

**Files:**
- Modify: `backend/app/api/semantic.py` (L86, L207, L939-970, L1642)
- Modify: `backend/app/mcp/tools/semantic.py` (L17, L102, L322-325, L511-522)
- Modify: `backend/app/api/schemas.py` (L915-916, L261, L318, L597-601, L671-672)

- [ ] **Step 1: Delete API route**

In `api/semantic.py`:
- Remove import of `_missing_evidence_service` / `SemanticMissingEvidenceService` (L86, L207)
- Delete `get_graph_set_missing_evidence` function (L939-970) and its `@router.get` decorator
- Remove the L1642 reference

- [ ] **Step 2: Delete MCP tool**

In `mcp/tools/semantic.py`:
- Delete `inspect_semantic_missing_evidence` tool definition (L322-325)
- Delete `_missing_evidence_summary` helper (L511-522)
- Remove import (L17, L102)

- [ ] **Step 3: Clean schemas.py**

- L915-916: remove `"submit_assertion"`, `"update_evidence_status"` from `_canonical_command_kinds()` fallback list
- L261: remove `evidence_status: Literal[...] | None` field from the edit request schema
- L318: remove `evidence_status: str` field from `SemanticEditAuditRead`
- L597-601: delete `SemanticMissingEvidenceSummary` class entirely
- L671-672: remove `assertion_kind: str` and `evidence_status: str` from `SemanticResourceRead` (only if they're not used elsewhere — grep first)

Run: `cd backend && grep -rn "SemanticMissingEvidenceSummary\|assertion_kind" app/ tests/`
Be careful — `assertion_kind` is used in many places for badge routing. Keep the field if frontend still uses it; remove only if grep is clean.

- [ ] **Step 4: Verify**

Run: `cd backend && uv run python -c "import app.api.semantic; import app.mcp.tools.semantic; import app.api.schemas; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/semantic.py backend/app/mcp/tools/semantic.py backend/app/api/schemas.py
git commit -m "refactor(api/mcp): remove /missing-evidence route, inspect_semantic_missing_evidence tool, evidence_status fields"
```

---

### Task 22: Remove `evidence_status` from edit API request/response

**Files:**
- Modify: `backend/app/api/semantic.py` (edit endpoints)
- Modify: `backend/app/api/schemas.py` (edit request schemas)

- [ ] **Step 1: Find edit endpoints**

Run: `cd backend && grep -n "previewSemanticEdit\|applySemanticEdit\|preview_semantic_edit\|apply_semantic_edit" app/api/semantic.py`

- [ ] **Step 2: Remove evidence_status handling**

In the request schema (likely `SemanticEditRequest`), remove `evidence_status` field.
In the endpoint handlers, remove any code that consumes `evidence_status` from the request.

- [ ] **Step 3: Verify**

Run: `cd backend && uv run python -c "from app.api.schemas import SemanticEditRequest; print(SemanticEditRequest.model_fields.keys())"`
Expected: no `evidence_status` in the output.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/semantic.py backend/app/api/schemas.py
git commit -m "refactor(api): drop evidence_status from edit endpoints"
```

---

## Phase 8: Frontend (Tasks 23-27)

### Task 23: Update `types.ts` + `semanticApi.ts`

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/semanticApi.ts`

- [ ] **Step 1: Remove legacy types**

In `types.ts`:
- L837: delete `export type SemanticEditEvidenceStatus = ...`
- L731-736: delete `SemanticMissingEvidenceSummary` interface
- L744: remove `evidence_status: string` from `SemanticStatementItem`
- L280-288: extend `EvidenceBinding` to include new fields: `id: string`, `fact_id: string`, `text: string`, `chunk_id?: string`, `evidence_artifact_id?: string`, `actor?: string`, `reason?: string`, `created_at?: string`

Add new type:
```typescript
export interface FactEvidenceBinding {
  id: string;
  fact_id: string;
  subject_iri: string;
  predicate_iri: string;
  object_value: string;
  graph_iri: string;
  chunk_id?: string | null;
  evidence_artifact_id?: string | null;
  document_filename?: string | null;
  sequence?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  text: string;
  text_preview?: string;
  actor?: string | null;
  reason?: string | null;
  created_at?: string | null;
}

export interface MissingEvidenceFactsResponse {
  count: number;
  fact_ids: string[];
}
```

- [ ] **Step 2: Update `semanticApi.ts`**

Remove from `semanticApi.ts`:
- L168, L182, L197, L211: `evidenceStatus?` parameters from `previewSemanticEdit` / `applySemanticEdit`
- L383-387: `getMissingEvidenceSummary` function
- Import of `SemanticEditEvidenceStatus` (L6)

Add new functions:
```typescript
export async function bindFactEvidence(
  request: AuthenticatedRequest,
  graphSetId: string,
  payload: {
    ontology_id: string;
    subject_iri: string;
    predicate_iri: string;
    object_value: string;
    object_is_iri?: boolean;
    object_datatype?: string;
    graph_iri?: string;
    fact_id?: string;
    chunk_id?: string;
    evidence_artifact_id?: string;
    document_filename?: string;
    sequence?: number;
    char_start?: number;
    char_end?: number;
    text: string;
    actor?: string;
    reason?: string;
  },
): Promise<FactEvidenceBinding> {
  return fetchJson(`/api/semantic/graph-sets/${graphSetId}/fact-evidence`, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: await authHeaders(request),
  });
}

export async function unbindFactEvidence(
  request: AuthenticatedRequest,
  graphSetId: string,
  bindingId: string,
): Promise<void> {
  await fetchJson(`/api/semantic/graph-sets/${graphSetId}/fact-evidence/${bindingId}`, {
    method: "DELETE",
    headers: await authHeaders(request),
  });
}

export async function getMissingEvidenceFacts(
  request: AuthenticatedRequest,
  graphSetId: string,
  limit?: number,
): Promise<MissingEvidenceFactsResponse> {
  const qs = limit ? `?limit=${limit}` : "";
  return fetchJson(`/api/semantic/graph-sets/${graphSetId}/missing-evidence-facts${qs}`, {
    headers: await authHeaders(request),
  });
}
```

(Adapt `fetchJson` / `authHeaders` / `AuthenticatedRequest` to whatever the file already uses.)

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run typecheck` (or `tsc --noEmit` — check package.json scripts)
Expected: Type errors only in files that haven't been migrated yet (FactAuditPage, GraphSetPage, etc. — those are fixed in Tasks 24-27).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/semanticApi.ts
git commit -m "refactor(frontend): update types + API clients for PG-backed evidence"
```

---

### Task 24: Update `FactAuditPage.tsx`

**Files:**
- Modify: `frontend/src/pages/FactAuditPage.tsx`

- [ ] **Step 1: Remove old evidence_status field type**

L86: remove `evidence_status: "with_evidence" | "missing_evidence" | "not_applicable"` from the row type (or keep as derived but mark as such).

L481: change condition from `selected.evidence_status === "missing_evidence"` to:
```typescript
{(selected.evidence_bindings?.length ?? 0) === 0 && (
  <Tag color="warning">{t("missing evidence")}</Tag>
)}
```

- [ ] **Step 2: Replace bind/unbind calls**

L246-292: replace `compileAndApplyProductCommand("bind_fact_evidence_text", ...)` with:
```typescript
await bindFactEvidence(request, graphSetId, {
  ontology_id: selected.ontology_id,
  subject_iri: selected.subject_iri,
  predicate_iri: selected.predicate_iri,
  object_value: selected.object_value,
  object_is_iri: selected.object_is_iri,
  graph_iri: selected.graph_iri,
  fact_id: selected.fact_id,
  text: evidenceText,
  actor: request.user?.id,
});
```

Replace `compileAndApplyProductCommand("unbind_fact_evidence", ...)` with:
```typescript
await unbindFactEvidence(request, graphSetId, bindingId);
```

- [ ] **Step 3: Update missing_evidence tab query**

The `kind=missing_evidence` read-model query still works (now PG-driven server-side); no client change needed. But verify the response shape still has `evidence_bindings` array per row (it does, just empty for missing ones).

- [ ] **Step 4: Smoke test**

Run: `cd frontend && npm run typecheck`
Expected: fewer type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/FactAuditPage.tsx
git commit -m "refactor(FactAuditPage): use new fact-evidence API; derive missing tag from bindings.length"
```

---

### Task 25: Add `EvidenceChunkPicker` component

**Files:**
- Create: `frontend/src/components/semantic/EvidenceChunkPicker.tsx`

- [ ] **Step 1: Build MVP picker (text-only, no PDF browser yet)**

```tsx
// frontend/src/components/semantic/EvidenceChunkPicker.tsx
import { useState } from "react";
import { Button, Input, Modal, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { FactEvidenceBinding } from "../../types";

interface Props {
  open: boolean;
  factId: string;
  onClose: () => void;
  onSubmit: (text: string, meta?: { document_filename?: string; sequence?: number }) => Promise<void>;
}

export function EvidenceChunkPicker({ open, factId, onClose, onSubmit }: Props) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [docName, setDocName] = useState<string | undefined>();
  const [sequence, setSequence] = useState<number | undefined>();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(text.trim(), { document_filename: docName, sequence });
      setText("");
      setDocName(undefined);
      setSequence(undefined);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("Add evidence")}
      onCancel={onClose}
      footer={[
        <Button key="cancel" onClick={onClose}>{t("Cancel")}</Button>,
        <Button key="ok" type="primary" loading={submitting} disabled={!text.trim()} onClick={handleSubmit}>
          {t("Add")}
        </Button>,
      ]}
    >
      <p style={{ marginBottom: 8 }}>
        <Tag>fact_id</Tag>
        <code style={{ fontSize: 12 }}>{factId.slice(0, 16)}…</code>
      </p>
      <Input.TextArea
        rows={6}
        placeholder={t("Paste or type evidence text")}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <Input
        style={{ marginTop: 8 }}
        placeholder={t("Document filename (optional)")}
        value={docName ?? ""}
        onChange={(e) => setDocName(e.target.value || undefined)}
      />
      <Input
        style={{ marginTop: 8 }}
        type="number"
        placeholder={t("Sequence (optional)")}
        value={sequence ?? ""}
        onChange={(e) => setSequence(e.target.value ? Number(e.target.value) : undefined)}
      />
    </Modal>
  );
}
```

Wire it into `FactAuditPage.tsx`:
```tsx
import { EvidenceChunkPicker } from "../components/semantic/EvidenceChunkPicker";

// State
const [pickerOpen, setPickerOpen] = useState(false);

// Button next to the evidence list:
<Button onClick={() => setPickerOpen(true)}>Add evidence</Button>

// At bottom of JSX:
<EvidenceChunkPicker
  open={pickerOpen}
  factId={selected.fact_id}
  onClose={() => setPickerOpen(false)}
  onSubmit={async (text, meta) => {
    await bindFactEvidence(request, graphSetId, {
      ontology_id: selected.ontology_id,
      subject_iri: selected.subject_iri,
      predicate_iri: selected.predicate_iri,
      object_value: selected.object_value,
      object_is_iri: selected.object_is_iri,
      graph_iri: selected.graph_iri,
      fact_id: selected.fact_id,
      text,
      document_filename: meta?.document_filename,
      sequence: meta?.sequence,
      actor: request.user?.id,
    });
    await reload();  // refresh list
  }}
/>
```

(Real PDF chunk browser is a follow-up; this MVP supports the user's primary workflow.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/semantic/EvidenceChunkPicker.tsx frontend/src/pages/FactAuditPage.tsx
git commit -m "feat(frontend): add EvidenceChunkPicker (MVP text-based) wired into FactAuditPage"
```

---

### Task 26: Delete `EvidenceBindingPanel` + update dependent pages

**Files:**
- Delete: `frontend/src/components/semantic/EvidenceBindingPanel.tsx`
- Modify: `frontend/src/pages/SemanticEditWorkbenchPage.tsx`
- Modify: `frontend/src/pages/SemanticImportExportPage.tsx`
- Modify: `frontend/src/pages/GraphSetPage.tsx`
- Modify: `frontend/src/pages/GraphGovernancePage.tsx`

- [ ] **Step 1: Delete EvidenceBindingPanel**

```bash
rm frontend/src/components/semantic/EvidenceBindingPanel.tsx
```

- [ ] **Step 2: Update SemanticEditWorkbenchPage**

L14: remove `SemanticEditEvidenceStatus` from imports.
L31: remove `evidenceStatus` state.
L89: remove the prop passing to EvidenceBindingPanel (or remove the panel usage entirely).
L130, L239-246: remove `evidenceStatus` from `previewSemanticEdit` / `applySemanticEdit` calls.

- [ ] **Step 3: Update SemanticImportExportPage**

L5: remove `SemanticEditEvidenceStatus` import.
L51: remove `evidenceStatus` state.
L112, L225-238: remove `evidenceStatus` from API calls.

- [ ] **Step 4: Update GraphSetPage**

L63: remove import of `getMissingEvidenceSummary`.
L95: replace summary call with `getMissingEvidenceFacts(request, gs.id)`.
L342-356: update the rendering — instead of `summary.dependencies`, render `{missingFacts.count} facts missing evidence`.

- [ ] **Step 5: Update GraphGovernancePage**

L199-200, L264-265: keep the missing_evidence gate display but source the count from the new `getMissingEvidenceFacts` API.
L342, L363-371: remove `audit.evidence_status` references (no longer in response).

- [ ] **Step 6: Verify frontend builds**

Run: `cd frontend && npm run typecheck`
Expected: clean (or fewer errors).

- [ ] **Step 7: Commit**

```bash
git add -A frontend/src/
git commit -m "refactor(frontend): delete EvidenceBindingPanel; update workbench/import/graph pages"
```

---

### Task 27: Clean `badges.tsx`, `EvidenceExplorerPanel`, i18n

**Files:**
- Modify: `frontend/src/components/semantic/badges.tsx`
- Modify: `frontend/src/components/semantic/EvidenceExplorerPanel.tsx`
- Modify: `frontend/src/i18n/zh.ts`

- [ ] **Step 1: Simplify badges.tsx**

- L7-14, L23, L35: remove `"missing_evidence"` from the `AssertionKind` union (it's no longer a kind — derived state instead).
- L54-73: simplify `EvidenceStatusBadge` to accept `bindingCount: number` and derive:

```tsx
export function EvidenceStatusBadge({ bindingCount }: { bindingCount: number }) {
  const { t } = useTranslation();
  if (bindingCount === 0) {
    return <Tag color="red">{t("missing evidence")}</Tag>;
  }
  return <Tag color="green">{bindingCount} {t("evidence")}</Tag>;
}
```

Update callers (search for `EvidenceStatusBadge` usages).

- [ ] **Step 2: Update EvidenceExplorerPanel**

L25-28, L36-58: change the missing tag condition to `(bindings?.length ?? 0) === 0`. Remove the `hideMissingTag` prop (no longer needed).

- [ ] **Step 3: Update i18n**

In `frontend/src/i18n/zh.ts`:
- L910: remove the "Statements written with missing evidence..." sentence (the write-path warning no longer exists).
- L1000: keep `"missing evidence": "证据缺失"`.

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: clean build.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "refactor(frontend): simplify badges, derive missing tag, clean i18n"
```

---

## Phase 9: Tests (Tasks 28-30)

### Task 28: Rewrite backend tests for new evidence model

**Files:**
- Modify: `backend/tests/test_semantic_command_compiler_stage2.py`
- Modify: `backend/tests/test_semantic_read_model.py`
- Modify: `backend/tests/test_semantic_sparql_templates.py`
- Modify: `backend/tests/test_semantic_migration_service.py`
- Modify: `backend/tests/test_semantic_phase5.py`
- Modify: `backend/tests/test_semantic_stage4_e2e.py`
- Modify: `backend/tests/test_semantic_reasoning.py`
- Modify: `backend/tests/test_semantic_validation.py`
- Modify: `backend/tests/test_evidence_rest_surface.py`
- Modify: any other test files that fail in the next step

- [ ] **Step 1: Run full backend test suite, capture failures**

Run: `cd backend && uv run pytest --tb=no -q 2>&1 | tail -100`
Note all failures.

- [ ] **Step 2: For each failing test, apply one of these strategies**

A. **Delete tests** of removed features (submit_assertion, update_evidence_status, op:evidenceStatus, reified FactClaim, derived_from_missing_evidence).

B. **Rewrite tests** of changed features:
- Tests asserting `_attach_evidence_bindings` SPARQL → rewrite to assert `_fetch_evidence_bindings_from_pg` calls.
- Tests asserting evidence_status marker on `create_entity` → flip the assertion (now absent).
- Tests asserting `missing_evidence_dependencies` in reasoning response → remove the assertion.
- Tests asserting `_fact_id_for` 3-tuple → update to expect 4-tuple algorithm via `compute_fact_id`.

C. **Add tests** for new behavior if not already covered (Task 4/5/7 tests cover the main paths; add more if specific edge cases emerged).

- [ ] **Step 3: Run full suite again**

Run: `cd backend && uv run pytest -v --tb=short 2>&1 | tail -50`
Expected: All tests pass. If failures remain, repeat Step 2.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: rewrite backend tests for PG-backed evidence model"
```

---

### Task 29: Add frontend tests for new components and pages

**Files:**
- Create: `frontend/src/components/semantic/EvidenceChunkPicker.test.tsx`
- Modify or create: `frontend/src/pages/FactAuditPage.test.tsx`
- Modify: any existing frontend tests that broke

- [ ] **Step 1: Run frontend test suite**

Run: `cd frontend && npm test -- --run 2>&1 | tail -50`
Note failures.

- [ ] **Step 2: Write EvidenceChunkPicker test**

```tsx
// frontend/src/components/semantic/EvidenceChunkPicker.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EvidenceChunkPicker } from "./EvidenceChunkPicker";

describe("EvidenceChunkPicker", () => {
  it("disables submit when text is empty", () => {
    const onSubmit = vi.fn();
    render(<EvidenceChunkPicker open={true} factId="a".repeat(64)} onClose={vi.fn()} onSubmit={onSubmit} />);
    expect(screen.getByText("Add").closest("button")).toBeDisabled();
  });

  it("calls onSubmit with trimmed text and meta", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<EvidenceChunkPicker open={true} factId="a".repeat(64)} onClose={vi.fn()} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByPlaceholderText(/Paste or type evidence text/i), {
      target: { value: "  hello world  " },
    });
    fireEvent.change(screen.getByPlaceholderText(/Document filename/i), {
      target: { value: "doc.pdf" },
    });
    fireEvent.click(screen.getByText("Add"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("hello world", { document_filename: "doc.pdf", sequence: undefined }));
  });
});
```

- [ ] **Step 3: Update FactAuditPage tests**

Adjust any tests that asserted on old command names (`bind_fact_evidence_text`) or `evidence_status` field.

- [ ] **Step 4: Run full frontend test suite**

Run: `cd frontend && npm test -- --run`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "test(frontend): add EvidenceChunkPicker tests, update FactAuditPage tests"
```

---

### Task 30: Run full test suite + start services for end-to-end check

- [ ] **Step 1: Backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 2: Frontend test suite**

Run: `cd frontend && npm test -- --run`
Expected: All tests pass.

- [ ] **Step 3: Backend lint / type check**

Run: `cd backend && uv run ruff check . && uv run mypy app/`
Expected: clean.

- [ ] **Step 4: Frontend type check + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: clean.

- [ ] **Step 5: Start backend**

Run: `cd backend && uv run uvicorn app.main:app --reload --port 8000 &`

- [ ] **Step 6: Start frontend**

Run: `cd frontend && npm run dev &`

- [ ] **Step 7: Manual end-to-end check**

Open browser at frontend URL:
1. Navigate to FactAuditPage for some graph_set
2. Verify no errors in console
3. Verify missing_evidence tab populates (facts without bindings)
4. Click a fact, "Add evidence", paste text, submit
5. Verify binding appears in evidence_bindings list
6. Verify fact no longer shows "missing evidence" tag
7. Verify fact no longer in missing_evidence tab after refresh

- [ ] **Step 8: Stop services**

```bash
pkill -f "uvicorn app.main"
pkill -f "vite"
```

- [ ] **Step 9: Commit (if any test fixes during E2E)**

```bash
git add -A
git commit -m "test: full suite passing post-refactor"
```

---

## Phase 10: Cleanup + Docs (Tasks 31-32)

### Task 31: Create `cleanup_legacy_evidence_rdf.py` script

**Files:**
- Create: `backend/scripts/cleanup_legacy_evidence_rdf.py`

- [ ] **Step 1: Write the cleanup script**

```python
# backend/scripts/cleanup_legacy_evidence_rdf.py
"""One-shot cleanup: remove all legacy evidence-related RDF triples from every
asserted_data graph in every graph_set. Run this once after deploying the new
PG-backed evidence system.

Removes:
  - ?s prov:wasDerivedFrom ?o
  - chunk IRI's 5 literal properties (sourceDocument, sequence, charStart, charEnd, text)
  - ?s op:evidenceStatus ?o
  - all op:FactClaim instances and their properties
"""
import argparse
import logging
import sys

logger = logging.getLogger(__name__)

PROV_WAS_DERIVED_FROM = "http://www.w3.org/ns/prov#wasDerivedFrom"
OP_NAMESPACE = "http://ontology-platform.local/semantic/op/"
TAG_NAMESPACE = "tag:ontology-platform.internal,2026:"

CLEANUP_SPARQL_TEMPLATE = """
DELETE WHERE {{
  GRAPH ?g {{
    {{
      ?s <{prov}> ?o .
    }} UNION {{
      ?s <{op}evidenceStatus> ?o .
    }} UNION {{
      ?s ?p ?o ;
         ?sp ?so .
      FILTER(?s = ?chunk && ?p IN (
        <{tag}sourceDocument>, <{tag}sequence>, <{tag}charStart>, <{tag}charEnd>, <{tag}text>
      ))
    }} UNION {{
      ?s a <{op}FactClaim> .
      ?s ?p ?o .
    }}
  }}
}}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print planned deletes without applying")
    parser.add_argument("--graph-set-id", help="Restrict to one graph_set")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.config import get_settings
    from app.services.semantic import SemanticService  # adapt to actual service entry

    settings = get_settings()
    service = SemanticService(settings=settings)

    graph_set_ids = (
        [args.graph_set_id] if args.graph_set_id else service.list_graph_set_ids()
    )

    for gs_id in graph_set_ids:
        logger.info("Cleaning graph_set %s (dry_run=%s)", gs_id, args.dry_run)
        # The actual SPARQL UPDATE should be split into 4 separate operations
        # because SPARQL doesn't support UNION in DELETE WHERE reliably.
        for sparql in [
            f"DELETE WHERE {{ GRAPH ?g {{ ?s <{PROV_WAS_DERIVED_FROM}> ?o . }} }}",
            f"DELETE WHERE {{ GRAPH ?g {{ ?s <{OP_NAMESPACE}evidenceStatus> ?o . }} }}",
            f"DELETE WHERE {{ GRAPH ?g {{ ?chunk ?p ?o . FILTER(?p IN (<{TAG_NAMESPACE}sourceDocument>, <{TAG_NAMESPACE}sequence>, <{TAG_NAMESPACE}charStart>, <{TAG_NAMESPACE}charEnd>, <{TAG_NAMESPACE}text>)) }} }}",
            f"DELETE WHERE {{ GRAPH ?g {{ ?s ?p ?o . ?s a <{OP_NAMESPACE}FactClaim> . }} }}",
        ]:
            if args.dry_run:
                logger.info("Would run: %s", sparql)
            else:
                service.execute_update(sparql, graph_set_id=gs_id)
                logger.info("Applied: %s", sparql)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke test (--dry-run)**

Run: `cd backend && uv run python scripts/cleanup_legacy_evidence_rdf.py --dry-run`
Expected: prints "Would run: ..." messages without errors.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/cleanup_legacy_evidence_rdf.py
git commit -m "feat(scripts): add one-shot cleanup for legacy evidence RDF triples"
```

---

### Task 32: Update docs (`CONTEXT.md`, `docs/semantic/`, ADRs)

**Files:**
- Modify: `CONTEXT.md` (if it mentions evidence storage)
- Modify: `docs/semantic/` relevant phase docs
- Modify: any ADR that references `op:evidenceStatus` or `prov:wasDerivedFrom`

- [ ] **Step 1: Find doc references**

Run: `cd /home/yangxiang/projects/ontology-platform && grep -rln "op:evidenceStatus\|prov:wasDerivedFrom\|FactClaim\|missing_evidence_dependencies\|derived_from_missing_evidence" CONTEXT.md docs/ 2>/dev/null`

- [ ] **Step 2: Update each doc**

For each match, edit to reflect the new architecture:
- Replace "stored as RDF prov:wasDerivedFrom" → "stored in Postgres fact_evidence_bindings table"
- Remove sections describing `op:evidenceStatus` literal mechanism
- Update data flow diagrams if present
- Note migration impact (old data discarded)

- [ ] **Step 3: Add changelog entry (if exists)**

Run: `cd /home/yangxiang/projects/ontology-platform && ls CHANGELOG* docs/CHANGELOG* 2>/dev/null`
If a changelog exists, append:

```
## [Unreleased] - Evidence storage refactor

- Evidence now stored in Postgres `fact_evidence_bindings` table at fact_id (sha256(s,p,o,g)) granularity
- Removed RDF-based evidence storage (prov:wasDerivedFrom + chunk literals, op:evidenceStatus marker, op:FactClaim reified assertions)
- missing_evidence is now derived (PG count = 0) instead of explicitly marked
- New REST endpoints: POST/DELETE /api/semantic/graph-sets/{gs}/fact-evidence, GET /missing-evidence-facts
- Removed endpoints: GET /api/semantic/graph-sets/{id}/missing-evidence
- Run `python scripts/cleanup_legacy_evidence_rdf.py` once after deploy to clean up old RDF triples
```

- [ ] **Step 4: Commit**

```bash
git add CONTEXT.md docs/ CHANGELOG*
git commit -m "docs: update for PG-backed evidence refactor"
```

---

## Self-Review Checklist

- **Spec coverage**: Each section of spec → at least one task. Verified:
  - PG schema → Task 2
  - fact_id util → Task 1
  - Repository → Task 3
  - New commands → Tasks 4-6
  - API → Task 7
  - Read path → Tasks 8-10
  - Delete legacy writes → Tasks 11-13
  - Delete legacy reads → Tasks 14-16
  - Clean services → Tasks 17-20
  - Clean API/MCP → Tasks 21-22
  - Frontend → Tasks 23-27
  - Tests → Tasks 28-30
  - Cleanup script → Task 31
  - Docs → Task 32

- **Placeholder scan**: No TBD/TODO; each task has actual code or concrete edit instructions.

- **Type consistency**: `FactEvidenceBinding` type used consistently across frontend (Task 23 introduces it; Task 25 picker uses `FactEvidenceBinding` indirectly; backend returns matching shape).

- **Open issues**:
  - The exact `compile_and_apply` executor wiring in Task 7 Step 2 is pseudocode — executor file structure may need slight adaptation.
  - `_list_asserted_fact_ids` helper in Task 10 needs to be added; pattern follows existing SPARQL helpers in the same service.
  - The cleanup script's `service.execute_update(...)` API name may need adapting to the actual service signature.

---

## Execution Handoff

User has already approved Subagent-Driven approach: dispatch a fresh subagent per task, review between tasks, fast iteration.

Start executing from Task 1.
