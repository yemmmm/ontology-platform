# Semantic Stage 1 — Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Stage 1 — Intake so BuildOverviewPage consumes a Phase 6 read-model + thin composer endpoint, and CompetencyQuestion validate runs SPARQL SELECT count over the active graph-set instead of Neo4j Cypher.

**Architecture:** Two parallel tracks under Approach C. Track A adds a Phase 6 read-model template `graph-set-staleness` (composer-driven — most fields come from Postgres, SPARQL only fetches missing-evidence count) plus a thin aggregation endpoint `/ontologies/{id}/build-overview`. Track B reroutes CompetencyQuestion validate through SPARQL with a new `sparql_count` kind. Legacy `/ontologies/{id}/versions`, `/ontologies/{id}/proposals`, `/projects/{id}/build-context` get Deprecation headers but stay alive until Stage 3.

**Tech Stack:** Python 3.14 + FastAPI + SQLAlchemy + Oxigraph (SPARQL) + pytest; React 18 + TypeScript + Vite + Playwright.

**Spec:** `docs/superpowers/specs/2026-07-06-semantic-stage1-intake-design.md`

---

## File Structure

### Track A — BuildOverview

| Path | Responsibility | Status |
| --- | --- | --- |
| `backend/app/services/semantic_sparql_templates.py` | Register the new template | Modify |
| `backend/app/services/semantic_read_model.py` | Branch on `graph-set-staleness`: assemble summary/detail envelopes by calling graph registry + derived-pointer repo + a single SPARQL for missing-evidence count | Modify |
| `backend/app/services/semantic_build_overview.py` | New: compose `/ontologies/{id}/build-overview` from Postgres brief/questions + the read-model envelope; derive `next_actions` | Create |
| `backend/app/api/interview.py` | New route `GET /ontologies/{id}/build-overview`; Deprecation header on `/projects/{id}/build-context` | Modify |
| `backend/app/api/metadata.py` | Deprecation header on `/ontologies/{id}/versions`, `/ontologies/{id}/proposals` | Modify |
| `backend/tests/test_semantic_read_model.py` | Extend with `graph-set-staleness` cases | Modify |
| `backend/tests/test_semantic_build_overview.py` | New: composer + next_actions tests | Create |
| `frontend/src/pages/workbenchTypes.ts` | Add `BuildOverviewResponse`, `GraphSetMemberStaleness`, `NextAction` | Modify |
| `frontend/src/pages/BuildOverviewPage.tsx` | Rewrite to consume new endpoint, drop timeline | Modify |
| `frontend/src/i18n/zh.ts` | New translation keys | Modify |
| `frontend/tests/workbench-smoke.spec.ts` | Add BuildOverview graph-set panel smoke | Modify |

### Track B — CompetencyQuestion validate

| Path | Responsibility | Status |
| --- | --- | --- |
| `backend/app/core/config.py` | New setting `competency_question_sparql_timeout_seconds` | Modify |
| `backend/app/services/semantic_sparql_runner.py` | New: validate user SPARQL is read-only SELECT, scope to graph-set members, run with timeout | Create |
| `backend/app/services/interview.py` | Rewrite `run_question_validation` for all three kinds | Modify |
| `backend/app/api/interview.py` | Inject Settings into `validate_competency_question` route | Modify |
| `backend/tests/test_semantic_sparql_runner.py` | New: guard tests | Create |
| `backend/tests/test_interview_service.py` | Extend with the three kinds | Create if missing, else modify |
| `frontend/src/pages/CompetencyQuestionsPage.tsx` | Modal editor adds `kind` selector + `sparql_count` fields | Modify |
| `frontend/tests/workbench-smoke.spec.ts` | Add validate smoke | Modify |

### Track C — Smoke contract

| Path | Responsibility | Status |
| --- | --- | --- |
| `docs/semantic/semantic-language-integration-test-plan.md` | Add Stage 1 entries | Modify |

---

## Track A — BuildOverview

### Task A1: Add `competency_question_sparql_timeout_seconds` setting

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add the failing test**

Create `backend/tests/test_settings.py`:

```python
from app.core.config import Settings


def test_competency_question_sparql_timeout_default():
    settings = Settings()
    assert settings.competency_question_sparql_timeout_seconds == 5.0


def test_competency_question_sparql_timeout_override():
    settings = Settings(competency_question_sparql_timeout_seconds=10.0)
    assert settings.competency_question_sparql_timeout_seconds == 10.0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && uv run pytest tests/test_settings.py -v
```

Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'competency_question_sparql_timeout_seconds'`.

- [ ] **Step 3: Add the field**

Edit `backend/app/core/config.py`. After the existing `semantic_query_timeout_seconds` line, add:

```python
    competency_question_sparql_timeout_seconds: float = Field(
        default=5.0, gt=0, le=60
    )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && uv run pytest tests/test_settings.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_settings.py
git commit -m "feat(semantic): add competency question SPARQL timeout setting"
```

---

### Task A2: Register `graph-set-staleness` template

**Files:**
- Modify: `backend/app/services/semantic_sparql_templates.py`
- Modify: `backend/tests/test_semantic_sparql_templates.py` (create if missing)

- [ ] **Step 1: Add the failing test**

Create `backend/tests/test_semantic_sparql_templates.py`:

```python
import pytest

from app.services.semantic_sparql_templates import get_template, list_templates


def test_graph_set_staleness_template_registered():
    template = get_template("graph-set-staleness")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("asserted_ontology", "asserted_data")
    assert template.needs_reasoning is True
    assert template.needs_rules is True
    assert template.default_limit == 1
    assert "missing-evidence" in template.body


def test_list_templates_includes_graph_set_staleness():
    names = {t.name for t in list_templates()}
    assert "graph-set-staleness" in names
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && uv run pytest tests/test_semantic_sparql_templates.py -v
```

Expected: FAIL with `KeyError: 'graph-set-staleness'`.

- [ ] **Step 3: Add the template**

Edit `backend/app/services/semantic_sparql_templates.py`. Add to `_TEMPLATES`:

```python
    "graph-set-staleness": ReadModelTemplate(
        name="graph-set-staleness",
        projection_version="semantic-read-v1",
        required_roles=("asserted_ontology", "asserted_data"),
        needs_reasoning=True,
        needs_rules=True,
        default_limit=1,
        assertion_kind="asserted",
        evidence_status="mixed",
        body="""# template: graph-set-staleness
        # Composer-driven. The SemanticReadModelService branch assembles
        # member/editable/staleness from Postgres; this SPARQL only fetches
        # the missing-evidence count across the active graph-set members.
        PREFIX op: <http://ontology-platform.local/semantic/op/>
        SELECT (COUNT(*) AS ?count) WHERE {
          VALUES ?g { {graph_iris} }
          GRAPH ?g { ?s op:evidenceStatus "missing_evidence" . }
        }
        """,
    ),
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && uv run pytest tests/test_semantic_sparql_templates.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_sparql_templates.py backend/tests/test_semantic_sparql_templates.py
git commit -m "feat(semantic): register graph-set-staleness read-model template"
```

---

### Task A3: Add `graph-set-staleness` summary composer in `SemanticReadModelService`

**Files:**
- Modify: `backend/app/services/semantic_read_model.py`
- Modify: `backend/tests/test_semantic_read_model.py`

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/test_semantic_read_model.py`:

```python
def test_graph_set_staleness_summary_assembles_members_and_count():
    """graph-set-staleness summary composes members, staleness, missing-evidence count."""
    from datetime import datetime, timezone

    from app.services.semantic_read_model import SemanticReadModelService

    # Fixture: scope resolver returns members + derived state + last edit timestamps
    resolution = _resolution(
        graph_iris=[
            "https://example/graph/ontology/x",
            "https://example/graph/data/x",
        ],
        reasoning={"status": "stale", "result_graph_iri": "https://example/graph/reasoning/x"},
        rule={"status": "current", "result_graph_iri": "https://example/graph/rule/x"},
    )
    store = FakeStore({
        "graph-set-staleness": [{"count": {"value": "3", "datatype": "http://www.w3.org/2001/XMLSchema#integer"}}],
    })
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=1,
    )

    envelope = service.read_model(
        graph_set_id="gs-1",
        model_name="graph-set-staleness",
        field_set="summary",
    )

    assert envelope["model_name"] == "graph-set-staleness"
    assert len(envelope["items"]) == 1
    item = envelope["items"][0]
    assert item["graph_set_id"] == "gs-1"
    assert item["missing_evidence_count"] == 3
    roles = {m["role"] for m in item["members"]}
    assert roles == {"asserted_ontology", "asserted_data"}
    # reasoning derived state was 'stale' in fixture
    rx_member = next(m for m in item["members"] if m["role"] == "asserted_data")
    assert rx_member["reasoning_stale"] is True
    assert rx_member["rule_stale"] is False


def test_graph_set_staleness_summary_handles_no_derived_pointers():
    """Missing derived pointers should yield null staleness, not a crash."""
    from app.services.semantic_read_model import SemanticReadModelService

    resolution = _resolution(graph_iris=["https://example/graph/data/x"])
    store = FakeStore({"graph-set-staleness": [{"count": {"value": "0"}}]})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=1,
    )

    envelope = service.read_model(
        graph_set_id="gs-1",
        model_name="graph-set-staleness",
        field_set="summary",
    )
    member = envelope["items"][0]["members"][0]
    # With no derived state from the resolver, staleness is None
    assert member["reasoning_stale"] is None
    assert member["rule_stale"] is None
```

Note: `_resolution` is the existing helper in this test module; the new assertions
assume the resolver already carries `derived_state` per member. If the existing
`_resolution` helper does not include this, extend it minimally to pass a `derived_state`
dict through.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_semantic_read_model.py::test_graph_set_staleness_summary_assembles_members_and_count tests/test_semantic_read_model.py::test_graph_set_staleness_summary_handles_no_derived_pointers -v
```

Expected: FAIL — the default read-model path returns rows from the FakeStore directly without composing the envelope shape we need.

- [ ] **Step 3: Implement the composer branch**

Edit `backend/app/services/semantic_read_model.py`. In `read_model`, before the existing
SPARQL-row iteration, branch on the template name. Use this structure:

```python
        if template.name == "graph-set-staleness":
            items = [self._compose_graph_set_staleness(scope, field_set)]
            return self._envelope(
                template=template,
                scope=scope,
                items=items,
                warnings=warnings,
            )
```

Add the helper methods:

```python
    def _compose_graph_set_stalence(self, scope, field_set):  # noqa: ANN001
        members: list[dict[str, Any]] = []
        for member in scope.members:
            members.append({
                "iri": member.graph_iri,
                "role": member.role,
                "editable": member.editable,
                "validation_stale": self._member_stale(member, "validation"),
                "reasoning_stale": self._member_stale(member, "reasoning"),
                "rule_stale": self._member_stale(member, "rule"),
                "last_semantic_edit_at": member.last_edit_at,
            })
            if field_set == "detail":
                members[-1]["derived_pointers"] = self._derived_pointers(member)
        missing = self._missing_evidence_count(scope)
        return {
            "graph_set_id": scope.graph_set_id,
            "members": members,
            "missing_evidence_count": missing,
            "last_semantic_edit_at": scope.last_edit_at,
        }

    def _member_stale(self, member, kind):  # noqa: ANN001
        state = (member.derived_state or {}).get(kind)
        if not state:
            return None
        return state.get("status") == "stale"

    def _derived_pointers(self, member):  # noqa: ANN001
        out = {}
        for kind in ("validation", "reasoning", "rule"):
            state = (member.derived_state or {}).get(kind)
            if state:
                out[kind] = {
                    "result_graph_iri": state.get("result_graph_iri"),
                    "became_current_at": state.get("became_current_at"),
                    "engine_name": state.get("engine_name"),
                    "engine_version": state.get("engine_version"),
                    "rule_version": state.get("rule_version"),
                    "shape_version": state.get("shape_version"),
                }
        return out

    def _missing_evidence_count(self, scope):  # noqa: ANN001
        template = get_template("graph-set-staleness")
        iris = [m.graph_iri for m in scope.members]
        query = template.body.replace("{graph_iris}", " ".join(f"<{i}>" for i in iris))
        result = self.rdf_store.query_read_model(
            query=query,
            graph_iris=iris,
            timeout_seconds=self.timeout_seconds,
            limit=1,
        )
        rows = list(self._rows(result))
        if not rows:
            return 0
        cell = rows[0].get("count", {})
        if isinstance(cell, dict):
            return int(cell.get("value", 0))
        return int(cell)
```

Note (typo guard): the method name must be `_compose_graph_set_staleness` (with the `a`).
If the codebase's existing `ScopeResolution` dataclass does not carry `members` with
`.editable`, `.last_edit_at`, `.derived_state`, or a top-level `.last_edit_at`, extend
`ScopeResolution` and the resolver to populate these from
`SemanticGraphRegistryService.list_members` and `SemanticDerivedResultPointerModel`
queries. Keep the dataclass fields optional/`None`-defaulted so existing tests still pass.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_semantic_read_model.py -v
```

Expected: PASS, including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_read_model.py backend/tests/test_semantic_read_model.py
git commit -m "feat(semantic): compose graph-set-staleness read model"
```

---

### Task A4: Create `semantic_build_overview` composer service

**Files:**
- Create: `backend/app/services/semantic_build_overview.py`
- Create: `backend/tests/test_semantic_build_overview.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_semantic_build_overview.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.services.semantic_build_overview import (
    BuildOverviewResponse,
    BuildOverviewService,
    NextAction,
)


def _service(read_model_payload, brief, questions):
    read_model = MagicMock()
    read_model.return_value = read_model_payload
    return BuildOverviewService(
        read_model=read_model,
        brief_summary=lambda session, project_id: brief,
        question_summary=lambda session, project_id: questions,
    )


def test_build_overview_composes_all_sections():
    payload = {
        "items": [{
            "graph_set_id": "gs-1",
            "members": [
                {"iri": "g://ont", "role": "asserted_ontology", "editable": True,
                 "validation_stale": False, "reasoning_stale": True, "rule_stale": False,
                 "last_semantic_edit_at": "2026-07-05T00:00:00Z"},
            ],
            "missing_evidence_count": 4,
            "last_semantic_edit_at": "2026-07-05T00:00:00Z",
        }],
    }
    brief = {"completeness": 0.5, "missing_fields": ["scope"]}
    questions = {"total": 3, "by_status": {"draft": 1, "approved": 0, "testable": 0,
                                            "passed": 2, "failed": 0}}
    service = _service(payload, brief, questions)

    response = service.build(session=MagicMock(), project_id="p-1",
                              ontology_id="o-1", graph_set_id="gs-1")

    assert isinstance(response, BuildOverviewResponse)
    assert response.graph_set.missing_evidence_count == 4
    assert response.project_brief.completeness == 0.5
    assert response.competency_questions.total == 3
    # next_actions includes complete_brief, approve_questions, recompute_derived, audit_missing_evidence
    keys = [a.key for a in response.next_actions]
    assert "complete_brief" in keys
    assert "approve_questions" in keys
    assert "recompute_derived" in keys
    assert "audit_missing_evidence" in keys
    # Top 3 only
    assert len(response.next_actions) == 3


def test_build_overview_next_actions_priority_order():
    """When all conditions trigger, the deterministic order wins."""
    payload = {"items": [{
        "graph_set_id": "gs-1", "members": [
            {"iri": "g://ont", "role": "asserted_ontology", "editable": True,
             "validation_stale": True, "reasoning_stale": True, "rule_stale": True,
             "last_semantic_edit_at": None},
        ],
        "missing_evidence_count": 1, "last_semantic_edit_at": None,
    }]}
    brief = {"completeness": 0.0, "missing_fields": ["a", "b"]}
    questions = {"total": 1, "by_status": {"draft": 1, "approved": 0, "testable": 0,
                                            "passed": 0, "failed": 0}}
    service = _service(payload, brief, questions)

    response = service.build(session=MagicMock(), project_id="p-1",
                              ontology_id="o-1", graph_set_id="gs-1")
    keys = [a.key for a in response.next_actions]
    assert keys == ["complete_brief", "approve_questions", "recompute_validation"]


def test_build_overview_no_actions_when_clean():
    payload = {"items": [{
        "graph_set_id": "gs-1", "members": [
            {"iri": "g://ont", "role": "asserted_ontology", "editable": True,
             "validation_stale": False, "reasoning_stale": False, "rule_stale": False,
             "last_semantic_edit_at": None},
        ],
        "missing_evidence_count": 0, "last_semantic_edit_at": None,
    }]}
    brief = {"completeness": 1.0, "missing_fields": []}
    questions = {"total": 0, "by_status": {"draft": 0, "approved": 0, "testable": 0,
                                            "passed": 0, "failed": 0}}
    service = _service(payload, brief, questions)

    response = service.build(session=MagicMock(), project_id="p-1",
                              ontology_id="o-1", graph_set_id="gs-1")
    assert response.next_actions == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_semantic_build_overview.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.semantic_build_overview'`.

- [ ] **Step 3: Implement the composer**

Create `backend/app/services/semantic_build_overview.py`:

```python
"""Compose /ontologies/{id}/build-overview from Postgres + the Phase 6 read model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class GraphSetMemberStaleness:
    iri: str
    role: str
    editable: bool
    validation_stale: bool | None
    reasoning_stale: bool | None
    rule_stale: bool | None
    last_semantic_edit_at: str | None


@dataclass(frozen=True)
class GraphSetStaleness:
    graph_set_id: str
    members: list[GraphSetMemberStaleness]
    missing_evidence_count: int
    last_semantic_edit_at: str | None


@dataclass(frozen=True)
class BriefSummary:
    completeness: float
    missing_fields: list[str]


@dataclass(frozen=True)
class CompetencyQuestionSummary:
    total: int
    by_status: dict[str, int]


@dataclass(frozen=True)
class NextAction:
    key: str
    label: str
    detail: str
    tab: str


@dataclass(frozen=True)
class BuildOverviewResponse:
    ontology_id: str
    graph_set: GraphSetStaleness
    project_brief: BriefSummary
    competency_questions: CompetencyQuestionSummary
    next_actions: list[NextAction] = field(default_factory=list)


_ReadModel = Callable[[str, str], dict[str, Any]]
_BriefSummary = Callable[[Any, str], BriefSummary]
_QuestionSummary = Callable[[Any, str], CompetencyQuestionSummary]


class BuildOverviewService:
    def __init__(
        self,
        read_model: _ReadModel,
        brief_summary: _BriefSummary,
        question_summary: _QuestionSummary,
    ) -> None:
        self._read_model = read_model
        self._brief_summary = brief_summary
        self._question_summary = question_summary

    def build(
        self,
        *,
        session: Any,
        project_id: str,
        ontology_id: str,
        graph_set_id: str,
    ) -> BuildOverviewResponse:
        payload = self._read_model(graph_set_id, "graph-set-staleness")
        items = payload.get("items") or []
        graph_set = self._parse_graph_set(items[0] if items else {})

        brief = self._brief_summary(session, project_id)
        questions = self._question_summary(session, project_id)
        actions = self._derive_next_actions(graph_set, brief, questions)

        return BuildOverviewResponse(
            ontology_id=ontology_id,
            graph_set=graph_set,
            project_brief=brief,
            competency_questions=questions,
            next_actions=actions,
        )

    @staticmethod
    def _parse_graph_set(payload: dict[str, Any]) -> GraphSetStaleness:
        members = [
            GraphSetMemberStaleness(
                iri=m["iri"],
                role=m["role"],
                editable=m.get("editable", True),
                validation_stale=m.get("validation_stale"),
                reasoning_stale=m.get("reasoning_stale"),
                rule_stale=m.get("rule_stale"),
                last_semantic_edit_at=m.get("last_semantic_edit_at"),
            )
            for m in payload.get("members", [])
        ]
        return GraphSetStaleness(
            graph_set_id=payload.get("graph_set_id", ""),
            members=members,
            missing_evidence_count=int(payload.get("missing_evidence_count", 0)),
            last_semantic_edit_at=payload.get("last_semantic_edit_at"),
        )

    @staticmethod
    def _derive_next_actions(
        graph_set: GraphSetStaleness,
        brief: BriefSummary,
        questions: CompetencyQuestionSummary,
    ) -> list[NextAction]:
        candidates: list[NextAction] = []

        if brief.completeness < 1.0:
            candidates.append(NextAction(
                key="complete_brief",
                label="完善 Project Brief",
                detail=f"{len(brief.missing_fields)} 个字段待处理",
                tab="brief",
            ))
        if questions.by_status.get("draft", 0) > 0:
            candidates.append(NextAction(
                key="approve_questions",
                label="批准能力问题",
                detail=f"{questions.by_status['draft']} 个草稿待批准",
                tab="questions",
            ))
        if any(m.validation_stale for m in graph_set.members):
            candidates.append(NextAction(
                key="recompute_validation",
                label="重新运行 SHACL 验证",
                detail="验证结果已过期",
                tab="governance",
            ))
        if any(m.reasoning_stale or m.rule_stale for m in graph_set.members):
            candidates.append(NextAction(
                key="recompute_derived",
                label="重新运行推理 / 规则",
                detail="派生结果已过期",
                tab="governance",
            ))
        if graph_set.missing_evidence_count > 0:
            candidates.append(NextAction(
                key="audit_missing_evidence",
                label="审查缺证据断言",
                detail=f"{graph_set.missing_evidence_count} 条",
                tab="evidence",
            ))
        return candidates[:3]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_semantic_build_overview.py -v
```

Expected: PASS for all three tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_build_overview.py backend/tests/test_semantic_build_overview.py
git commit -m "feat(semantic): add BuildOverview composer service"
```

---

### Task A5: Add `/ontologies/{id}/build-overview` route

**Files:**
- Modify: `backend/app/api/interview.py`
- Modify: `backend/tests/test_interview_api.py` (create if missing)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_interview_api.py` (create if missing — see existing
interview service tests for fixture style):

```python
def test_build_overview_route_returns_200(monkeypatch):
    """The route wires BuildOverviewService into a FastAPI response."""
    from app.api.interview import app  # adjust import to match actual router object
    from fastapi.testclient import TestClient

    # Patch the service factory used by the route to return deterministic data.
    monkeypatch.setattr(
        "app.api.interview._build_overview_service",
        lambda session, rdf_store, settings: _StubService(),
    )
    client = TestClient(app)
    response = client.get("/ontologies/o-1/build-overview?project=p-1")
    assert response.status_code == 200
    body = response.json()
    assert body["ontology_id"] == "o-1"
    assert body["graph_set"]["graph_set_id"]
    assert "next_actions" in body


def test_build_overview_route_returns_404_when_no_active_graph_set(monkeypatch):
    from app.api.interview import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "app.api.interview._active_graph_set_for_ontology",
        lambda session, ontology_id: None,
    )
    client = TestClient(app)
    response = client.get("/ontologies/o-1/build-overview?project=p-1")
    assert response.status_code == 404
    assert "active graph-set" in response.json()["detail"].lower()


class _StubService:
    def build(self, *, session, project_id, ontology_id, graph_set_id):
        from app.services.semantic_build_overview import (
            BuildOverviewResponse, BriefSummary, CompetencyQuestionSummary,
            GraphSetStaleness, GraphSetMemberStaleness,
        )
        return BuildOverviewResponse(
            ontology_id=ontology_id,
            graph_set=GraphSetStaleness(
                graph_set_id=graph_set_id, members=[
                    GraphSetMemberStaleness("g://x", "asserted_ontology", True,
                                             False, False, False, None),
                ],
                missing_evidence_count=0, last_semantic_edit_at=None,
            ),
            project_brief=BriefSummary(1.0, []),
            competency_questions=CompetencyQuestionSummary(0, {}),
            next_actions=[],
        )
```

If `test_interview_api.py` does not exist yet, create it. Use the same `in_memory_session`
fixture from `conftest.py` plus a FastAPI `TestClient` setup against the `interview.router`
registered into a fresh `FastAPI()` app inside the test module.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_interview_api.py -v
```

Expected: FAIL — route not registered, `_build_overview_service` patch target missing.

- [ ] **Step 3: Implement the route**

Edit `backend/app/api/interview.py`. Add at the top:

```python
from app.services.semantic_build_overview import BuildOverviewService
from app.services.semantic_read_model import SemanticReadModelService
from app.services.interview import brief_summary_for_overview, question_summary_for_overview
```

Add the lookup + factory helpers (place near the existing router definition):

```python
def _active_graph_set_for_ontology(session, ontology_id):
    """Return the active graph-set id for an ontology, or None."""
    from app.repositories.models import SemanticGraphSetModel
    return session.scalar(
        select(SemanticGraphSetModel.id)
        .where(
            SemanticGraphSetModel.scope_type == "ontology",
            SemanticGraphSetModel.scope_id == ontology_id,
            SemanticGraphSetModel.status == "active",
        )
        .order_by(SemanticGraphSetModel.updated_at.desc())
        .limit(1)
    )


def _build_overview_service(session, rdf_store, settings):
    read_model_service = SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=_read_model_scope_resolver(session),
        timeout_seconds=settings.semantic_query_timeout_seconds,
        default_limit=1,
    )

    def _read(graph_set_id: str, model_name: str):
        return read_model_service.read_model(
            graph_set_id=graph_set_id,
            model_name=model_name,
            field_set="summary",
        )

    return BuildOverviewService(
        read_model=_read,
        brief_summary=brief_summary_for_overview,
        question_summary=question_summary_for_overview,
    )
```

Add the route at the bottom of the file:

```python
@router.get("/ontologies/{ontology_id}/build-overview")
def get_build_overview(
    ontology_id: str,
    project_id: str = "",
    session: Session = Depends(get_db_session),
    rdf_store=Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    graph_set_id = _active_graph_set_for_ontology(session, ontology_id)
    if not graph_set_id:
        raise HTTPException(
            status_code=404,
            detail=f"ontology {ontology_id} has no active graph-set",
        )
    service = _build_overview_service(session, rdf_store, settings)
    response = service.build(
        session=session,
        project_id=project_id,
        ontology_id=ontology_id,
        graph_set_id=graph_set_id,
    )
    # Serialize dataclasses to dicts for FastAPI
    from dataclasses import asdict
    return asdict(response)
```

If `brief_summary_for_overview` and `question_summary_for_overview` do not exist in
`backend/app/services/interview.py`, add them:

```python
def brief_summary_for_overview(session, project_id):
    brief = session.scalar(select(ProjectBriefModel).where(ProjectBriefModel.project_id == project_id))
    if not brief:
        return BriefSummary(completeness=0.0, missing_fields=[])
    fields = brief.content or {}
    states = brief.field_states or {}
    missing = [k for k, v in states.items() if v != "confirmed"] + [
        k for k in ("domain_name", "business_goal", "scope", "core_concepts",
                    "identity_rules", "expected_granularity", "data_sources",
                    "boundaries", "terminology", "inference_scope")
        if k not in fields
    ]
    completeness = 1.0 - (len(missing) / 10) if fields else 0.0
    return BriefSummary(completeness=completeness, missing_fields=missing)


def question_summary_for_overview(session, project_id):
    rows = session.scalars(
        select(CompetencyQuestionModel).where(
            CompetencyQuestionModel.project_id == project_id,
            CompetencyQuestionModel.active.is_(True),
        )
    ).all()
    by_status = {"draft": 0, "approved": 0, "testable": 0, "passed": 0, "failed": 0}
    for q in rows:
        by_status[q.status] = by_status.get(q.status, 0) + 1
    return CompetencyQuestionSummary(total=len(rows), by_status=by_status)
```

And import the dataclasses into the service module:

```python
from app.services.semantic_build_overview import (
    BriefSummary, CompetencyQuestionSummary,
)
```

If `_read_model_scope_resolver` does not exist, look up how the existing
`/graph-sets/{id}/read-models/{name}` route constructs its `SemanticReadModelService` and
mirror that wiring. The wiring lives in `backend/app/api/semantic.py`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_interview_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/interview.py backend/app/services/interview.py backend/tests/test_interview_api.py
git commit -m "feat(semantic): add /ontologies/{id}/build-overview route"
```

---

### Task A6: Add Deprecation headers on legacy BuildOverview endpoints

**Files:**
- Modify: `backend/app/api/interview.py`
- Modify: `backend/app/api/metadata.py`
- Modify: `backend/tests/test_interview_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_interview_api.py`:

```python
def test_build_context_legacy_route_returns_deprecation_header(monkeypatch):
    from app.api.interview import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/projects/p-1/build-context")
    # Even if the route returns 200 or 422, the header must be present.
    assert response.headers.get("Deprecation") == "true"
    assert "Sunset" in response.headers


def test_versions_route_returns_deprecation_header():
    from app.api.metadata import app  # adjust import to the actual router object
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/ontologies/o-1/versions")
    assert response.headers.get("Deprecation") == "true"


def test_proposals_route_returns_deprecation_header():
    from app.api.metadata import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/ontologies/o-1/proposals")
    assert response.headers.get("Deprecation") == "true"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_interview_api.py -v
```

Expected: FAIL — headers absent.

- [ ] **Step 3: Add a shared deprecation dependency**

Edit `backend/app/api/interview.py`. Add near the imports:

```python
from fastapi import Response

_LEGACY_SUNSET = "Sat, 1 Nov 2026 00:00:00 GMT"


def _mark_deprecated(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _LEGACY_SUNSET
```

In `/projects/{project_id}/build-context`, inject `response: Response = Depends()` (or pass
the existing response through) and call `_mark_deprecated(response)` before returning.

Repeat for the version/proposal list routes in `backend/app/api/metadata.py`. Look up the
exact function names with `grep -nE "@router.get" backend/app/api/metadata.py | grep -E "versions|proposals"`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_interview_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/interview.py backend/app/api/metadata.py backend/tests/test_interview_api.py
git commit -m "feat(semantic): deprecate legacy BuildOverview endpoints"
```

---

### Task A7: Update frontend types

**Files:**
- Modify: `frontend/src/pages/workbenchTypes.ts`

- [ ] **Step 1: Inspect current file**

```bash
grep -nE "BuildContext|OntologyVersionSummary|ProposalSummary" frontend/src/pages/workbenchTypes.ts
```

- [ ] **Step 2: Add the new types**

Append to `frontend/src/pages/workbenchTypes.ts`:

```typescript
export type GraphSetMemberStaleness = {
  iri: string;
  role: "asserted_ontology" | "asserted_data" | "reasoning_result" | "rule_result" | "validation_result" | string;
  editable: boolean;
  validation_stale: boolean | null;
  reasoning_stale: boolean | null;
  rule_stale: boolean | null;
  last_semantic_edit_at: string | null;
};

export type GraphSetStaleness = {
  graph_set_id: string;
  members: GraphSetMemberStaleness[];
  missing_evidence_count: number;
  last_semantic_edit_at: string | null;
};

export type BriefSummary = {
  completeness: number;
  missing_fields: string[];
};

export type CompetencyQuestionSummary = {
  total: number;
  by_status: Record<string, number>;
};

export type NextAction = {
  key: string;
  label: string;
  detail: string;
  tab: string;
};

export type BuildOverviewResponse = {
  ontology_id: string;
  graph_set: GraphSetStaleness;
  project_brief: BriefSummary;
  competency_questions: CompetencyQuestionSummary;
  next_actions: NextAction[];
};
```

- [ ] **Step 3: Verify the types compile**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/workbenchTypes.ts
git commit -m "feat(frontend): add BuildOverviewResponse types"
```

---

### Task A8: Rewrite `BuildOverviewPage`

**Files:**
- Modify: `frontend/src/pages/BuildOverviewPage.tsx`
- Modify: `frontend/src/i18n/zh.ts`

- [ ] **Step 1: Add i18n keys**

Append to `frontend/src/i18n/zh.ts` under the existing build-overview section:

```typescript
"活跃 Graph Set": "活跃 Graph Set",
"成员图": "成员图",
"派生结果新鲜度": "派生结果新鲜度",
"Validation": "Validation",
"Reasoning": "Reasoning",
"Rule": "Rule",
"已过期": "已过期",
"最新": "最新",
"未知": "未知",
"Missing evidence": "Missing evidence",
"前往 Governance": "前往 Governance",
"当前本体还没有活跃的 graph-set。请先到 Graph Set 页面创建。": "当前本体还没有活跃的 graph-set。请先到 Graph Set 页面创建。",
```

If these keys already exist or your i18n loader auto-falls-back to source strings, skip
the duplicate entries.

- [ ] **Step 2: Rewrite the page**

Replace the contents of `frontend/src/pages/BuildOverviewPage.tsx` with:

```tsx
import { Alert, Card, Skeleton, Tag } from "antd";
import { ArrowRight, CheckCircle2, Circle, Network, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useT } from "../i18n";
import type {
  BuildOverviewResponse,
  GraphSetMemberStaleness,
  WorkbenchNavigate,
  WorkbenchRequest,
} from "./workbenchTypes";

export type BuildOverviewPageProps = {
  projectId: string;
  ontologyId: string;
  readOnly?: boolean;
  request: WorkbenchRequest;
  onNavigate: WorkbenchNavigate;
};

function StalenessTag({ value }: { value: boolean | null }) {
  const t = useT();
  if (value === null) return <Tag>{t("未知")}</Tag>;
  return value ? <Tag color="orange">{t("已过期")}</Tag> : <Tag color="green">{t("最新")}</Tag>;
}

export function BuildOverviewPage({
  projectId,
  ontologyId,
  readOnly = false,
  request,
  onNavigate,
}: BuildOverviewPageProps) {
  const t = useT();
  const [data, setData] = useState<BuildOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await request<BuildOverviewResponse>(
        `/ontologies/${ontologyId}/build-overview?project=${encodeURIComponent(projectId)}`,
      );
      setData(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [ontologyId, projectId, request]);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <Card className="panel"><Skeleton active paragraph={{ rows: 8 }} /></Card>;
  if (error) return <Alert type="error" showIcon message={t("构建概览加载失败")} description={error}
    action={<button className="secondaryButton" onClick={() => void load()}>{t("重试")}</button>} />;
  if (!data) return <Alert type="warning" showIcon message={t("当前本体还没有活跃的 graph-set。请先到 Graph Set 页面创建。")}
    action={<button className="secondaryButton" onClick={() => onNavigate("graph-set")}>{t("前往 Graph Set")}</button>} />;

  const hasStaleReasoning = data.graph_set.members.some((m) => m.reasoning_stale);
  const hasStaleRule = data.graph_set.members.some((m) => m.rule_stale);
  const hasStaleValidation = data.graph_set.members.some((m) => m.validation_stale);

  return (
    <div className="workspaceStack">
      <div className="pageSubHeader">
        <div>
          <h2>{t("构建概览")}</h2>
          <p>{t("基于活跃 graph-set 的状态、派生结果新鲜度与下一步操作。")}</p>
        </div>
        <div className="rowActions">
          {readOnly && <Tag color="blue">{t("只读")}</Tag>}
          <button className="secondaryButton" onClick={() => void load()}><RefreshCw size={15} />{t("刷新")}</button>
        </div>
      </div>

      <div className="metricGrid">
        <button className="metric" onClick={() => onNavigate("brief")}>
          <div><CheckCircle2 size={18} /></div>
          <strong>{Math.round(data.project_brief.completeness * 100)}%</strong>
          <span>{t("Brief 完整度")}</span>
        </button>
        <button className="metric" onClick={() => onNavigate("questions")}>
          <div><Circle size={18} /></div>
          <strong>{data.competency_questions.total}</strong>
          <span>{t("能力问题")}</span>
        </button>
        <button className="metric" onClick={() => onNavigate("evidence")}>
          <div><Network size={18} /></div>
          <strong>{data.graph_set.missing_evidence_count}</strong>
          <span>{t("Missing evidence")}</span>
        </button>
        <button className="metric" onClick={() => onNavigate("governance")}>
          <div><CheckCircle2 size={18} /></div>
          <strong>{data.graph_set.members.length}</strong>
          <span>{t("成员图")}</span>
        </button>
      </div>

      <Card className="panel" title={t("活跃 Graph Set 状态")}>
        <div className="dataList">
          {data.graph_set.members.map((m: GraphSetMemberStaleness) => (
            <div className="dataRow" key={m.iri}>
              <span className="rowContent">
                <strong>{m.role}</strong>
                <span>{m.iri}</span>
                <span style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                  <Tag>{m.editable ? t("可编辑") : t("已锁定")}</Tag>
                  <span>V{`: `}<StalenessTag value={m.validation_stale} /></span>
                  <span>R{`: `}<StalenessTag value={m.reasoning_stale} /></span>
                  <span>Rule{`: `}<StalenessTag value={m.rule_stale} /></span>
                </span>
              </span>
            </div>
          ))}
        </div>
      </Card>

      <Card className="panel" title={t("派生结果新鲜度")}>
        <div className="pageGrid">
          <div>
            <strong>{t("Validation")}</strong>
            <div style={{ marginTop: 8 }}><StalenessTag value={hasStaleValidation} /></div>
          </div>
          <div>
            <strong>{t("Reasoning")}</strong>
            <div style={{ marginTop: 8 }}><StalenessTag value={hasStaleReasoning} /></div>
          </div>
          <div>
            <strong>{t("Rule")}</strong>
            <div style={{ marginTop: 8 }}><StalenessTag value={hasStaleRule} /></div>
          </div>
        </div>
        {(hasStaleValidation || hasStaleReasoning || hasStaleRule) && (
          <button className="secondaryButton" style={{ marginTop: 16 }}
            onClick={() => onNavigate("governance")}>{t("前往 Governance")}</button>
        )}
      </Card>

      <Card className="panel" title={t("下一步")}>
        {data.next_actions.length ? (
          <div className="dataList">
            {data.next_actions.map((action) => (
              <button className="dataRow" key={action.key} onClick={() => onNavigate(action.tab)}>
                <span className="rowContent"><strong>{action.label}</strong><span>{action.detail}</span></span>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        ) : (
          <div className="emptyState">{t("当前没有确定性的待办操作。")}</div>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors. If `WorkbenchNavigate` signature rejects `"graph-set"` or `"evidence"`
as a tab, extend the type union to include those.

- [ ] **Step 4: Run existing Playwright smoke**

```bash
cd frontend && npx playwright test workbench-smoke --reporter=list
```

Expected: existing BuildOverview smoke will fail because the timeline is gone. Update the
assertions in `frontend/tests/workbench-smoke.spec.ts` to look for the new "活跃 Graph Set
状态" header instead. (See Task A9.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/BuildOverviewPage.tsx frontend/src/i18n/zh.ts
git commit -m "feat(frontend): rewrite BuildOverviewPage on graph-set read model"
```

---

### Task A9: Update Playwright smoke for BuildOverview

**Files:**
- Modify: `frontend/tests/workbench-smoke.spec.ts`

- [ ] **Step 1: Add the test**

Append to `frontend/tests/workbench-smoke.spec.ts` (or replace the existing
BuildOverview-related block):

```typescript
test("BuildOverview shows graph-set panel and next actions", async ({ page }: Page & { }) => {
  // Mock the new composer endpoint. Adjust the route registration URL to match the
  // Playwright base URL set in playwright.config.ts.
  await page.route("**/ontologies/*/build-overview*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ontology_id: "ontology-1",
        graph_set: {
          graph_set_id: "gs-1",
          members: [
            { iri: "https://x/graph/ontology/1", role: "asserted_ontology", editable: true,
              validation_stale: false, reasoning_stale: true, rule_stale: false,
              last_semantic_edit_at: "2026-07-05T00:00:00Z" },
            { iri: "https://x/graph/data/1", role: "asserted_data", editable: true,
              validation_stale: false, reasoning_stale: true, rule_stale: false,
              last_semantic_edit_at: "2026-07-05T00:00:00Z" },
          ],
          missing_evidence_count: 4,
          last_semantic_edit_at: "2026-07-05T00:00:00Z",
        },
        project_brief: { completeness: 0.5, missing_fields: ["scope"] },
        competency_questions: { total: 3, by_status: { draft: 1, approved: 0, testable: 0,
                                                       passed: 2, failed: 0 } },
        next_actions: [
          { key: "complete_brief", label: "完善 Project Brief", detail: "1 个字段待处理", tab: "brief" },
          { key: "approve_questions", label: "批准能力问题", detail: "1 个草稿待批准", tab: "questions" },
          { key: "recompute_derived", label: "重新运行推理 / 规则", detail: "派生结果已过期", tab: "governance" },
        ],
      }),
    });
  });

  await page.goto("?project=project-1&ontology=ontology-1&tab=overview");
  await expect(page.getByText("活跃 Graph Set 状态")).toBeVisible();
  await expect(page.getByText("Missing evidence")).toBeVisible();
  await expect(page.getByText("完善 Project Brief")).toBeVisible();
  await expect(page.getByText("重新运行推理 / 规则")).toBeVisible();
});
```

- [ ] **Step 2: Run the test**

```bash
cd frontend && npx playwright test workbench-smoke --reporter=list
```

Expected: PASS. Existing BuildOverview timeline assertions need to be removed/replaced in
the same file (grep for `gathering` / `schema_draft`).

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/workbench-smoke.spec.ts
git commit -m "test(frontend): smoke for BuildOverview graph-set panel"
```

---

## Track B — CompetencyQuestion validate

### Task B1: Create SPARQL runner helper

**Files:**
- Create: `backend/app/services/semantic_sparql_runner.py`
- Create: `backend/tests/test_semantic_sparql_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_semantic_sparql_runner.py`:

```python
import pytest

from app.services.semantic_sparql_runner import (
    SparqlCountResult,
    SparqlGuardError,
    run_select_count,
)


def _store(rows):
    class _Store:
        def __init__(self, rows):
            self._rows = rows
            self.last_query = None

        def query_sparql(self, query, timeout_seconds, limit):
            self.last_query = query
            class _R:  # noqa: ANN001
                def __init__(self, rows):
                    self.result = {"results": {"bindings": rows}}
                    self.result_format = "application/sparql-results+json"
            return _R(self._rows)
    return _Store(rows)


def test_run_select_count_returns_first_count_column():
    store = _store([{"count": {"value": "5", "datatype": "http://www.w3.org/2001/XMLSchema#integer"}}])
    result = run_select_count(
        store=store,
        query="SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }",
        graph_iris=["https://x/g"],
        timeout_seconds=5,
    )
    assert isinstance(result, SparqlCountResult)
    assert result.count == 5
    assert "?g" in store.last_query or "VALUES ?g" in store.last_query


def test_run_select_count_rejects_construct():
    store = _store([])
    with pytest.raises(SparqlGuardError) as exc:
        run_select_count(
            store=store,
            query="CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )
    assert "only SELECT allowed" in str(exc.value)


def test_run_select_count_rejects_insert():
    store = _store([])
    with pytest.raises(SparqlGuardError):
        run_select_count(
            store=store,
            query="INSERT DATA { <a> <b> <c> }",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_rejects_ask():
    store = _store([])
    with pytest.raises(SparqlGuardError):
        run_select_count(
            store=store,
            query="ASK { ?s ?p ?o }",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_rejects_load_keyword():
    store = _store([])
    with pytest.raises(SparqlGuardError):
        run_select_count(
            store=store,
            query="SELECT * WHERE { ?s ?p ?o } LOAD <file>",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )


def test_run_select_count_missing_count_column():
    store = _store([{"foo": {"value": "1"}}])
    with pytest.raises(SparqlGuardError) as exc:
        run_select_count(
            store=store,
            query="SELECT (COUNT(*) AS ?foo) WHERE { ?s ?p ?o }",
            graph_iris=["https://x/g"],
            timeout_seconds=5,
        )
    assert "missing count" in str(exc.value).lower()


def test_run_select_count_empty_result_is_zero():
    store = _store([])
    result = run_select_count(
        store=store,
        query="SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }",
        graph_iris=["https://x/g"],
        timeout_seconds=5,
    )
    assert result.count == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_semantic_sparql_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the runner**

Create `backend/app/services/semantic_sparql_runner.py`:

```python
"""Read-only SPARQL SELECT runner with graph scoping and timeout."""

from __future__ import annotations

import re
from dataclasses import dataclass


class SparqlGuardError(ValueError):
    """Raised when a user-provided SPARQL violates the read-only SELECT contract."""


@dataclass(frozen=True)
class SparqlCountResult:
    count: int


_FORBIDDEN_KEYWORDS = (
    "INSERT",
    "DELETE",
    "LOAD",
    "CLEAR",
    "DROP",
    "CREATE",
    "MODIFY",
    "ADD",
    "MOVE",
    "COPY",
)


def _strip_comments(query: str) -> str:
    return re.sub(r"#.*$", "", query, flags=re.MULTILINE)


def _first_keyword(query: str) -> str:
    cleaned = _strip_comments(query).strip()
    if not cleaned:
        return ""
    return cleaned.split(None, 1)[0].upper()


def _validate_select_only(query: str) -> None:
    if _first_keyword(query) != "SELECT":
        raise SparqlGuardError("only SELECT allowed")
    upper = _strip_comments(query).upper()
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            raise SparqlGuardError("only SELECT allowed")


def _scope_query_to_graphs(query: str, graph_iris: list[str]) -> str:
    """Wrap the user SELECT in an outer SELECT that constrains ?g via VALUES.

    The user query must reference GRAPH ?g { ... } in its WHERE clause to read
    anything; otherwise it reads nothing. This is intentional — we will not
    parse the user query beyond the keyword allow-list.
    """
    values = " ".join(f"<{iri}>" for iri in graph_iris)
    return (
        f"SELECT (COUNT(*) AS ?count) WHERE {{ "
        f"VALUES ?g {{ {values} }} "
        f"{_strip_comments(query)} "
        f"}} LIMIT 1"
    )


def run_select_count(
    *,
    store,
    query: str,
    graph_iris: list[str],
    timeout_seconds: float,
) -> SparqlCountResult:
    _validate_select_only(query)
    wrapped = _scope_query_to_graphs(query, graph_iris)
    result = store.query_sparql(
        query=wrapped, timeout_seconds=timeout_seconds, limit=1,
    )
    bindings = result.result.get("results", {}).get("bindings", []) if isinstance(
        result.result, dict
    ) else []
    if not bindings:
        return SparqlCountResult(count=0)
    row = bindings[0]
    if "count" not in row:
        raise SparqlGuardError("sparql result missing count column")
    return SparqlCountResult(count=int(row["count"]["value"]))
```

Note: the scoping strategy wraps the user query rather than parsing it. This is the
simpler of the two options flagged in § 9 of the spec. The wrapper relies on the user
query referencing `GRAPH ?g { … }`; if a query has no `GRAPH` clause, the wrapper yields
no rows and the count is 0. Document this in the API and in the CompetencyQuestionsPage
editor placeholder text.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_semantic_sparql_runner.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/semantic_sparql_runner.py backend/tests/test_semantic_sparql_runner.py
git commit -m "feat(semantic): add read-only SPARQL SELECT count runner"
```

---

### Task B2: Resolve active graph-set members for a competency question

**Files:**
- Modify: `backend/app/services/interview.py`
- Modify: `backend/tests/test_interview_service.py` (create if missing)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_interview_service.py`:

```python
def test_active_data_and_ontology_graphs_for_question_returns_member_iris(
    in_memory_session,
):
    """The helper returns ontology + data member IRIs for the question's ontology."""
    from app.repositories.models import (
        SemanticGraphSetModel, SemanticGraphSetMemberModel,
        CompetencyQuestionModel, OntologyModel, ProjectModel,
    )
    from app.services.interview import active_data_and_ontology_graphs_for_question

    in_memory_session.add(ProjectModel(id="p-1", name="P"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.add(CompetencyQuestionModel(
        id="q-1", project_id="p-1", ontology_id="o-1",
        question="q", position=0, status="testable",
        query_definition={}, source_brief_fields=[],
    ))
    in_memory_session.add(SemanticGraphSetModel(
        id="gs-1", name="GS", scope_type="ontology", scope_id="o-1", status="active",
    ))
    for role, iri in [
        ("asserted_ontology", "https://x/graph/ontology/o-1"),
        ("asserted_data", "https://x/graph/data/o-1"),
    ]:
        in_memory_session.add(SemanticGraphSetMemberModel(
            id=f"m-{role}", graph_set_id="gs-1", graph_iri=iri, role=role,
        ))
    in_memory_session.commit()

    iris = active_data_and_ontology_graphs_for_question(in_memory_session, "q-1")
    assert "https://x/graph/ontology/o-1" in iris
    assert "https://x/graph/data/o-1" in iris
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && uv run pytest tests/test_interview_service.py::test_active_data_and_ontology_graphs_for_question_returns_member_iris -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the helper**

Edit `backend/app/services/interview.py`. Add:

```python
def active_data_and_ontology_graphs_for_question(session, question_id):
    """Return ontology + data member IRIs for the question's ontology graph-set."""
    question = _question(session, question_id)
    rows = session.execute(
        select(SemanticGraphSetMemberModel.graph_iri, SemanticGraphSetMemberModel.role)
        .join(SemanticGraphSetModel, SemanticGraphSetModel.id == SemanticGraphSetMemberModel.graph_set_id)
        .where(
            SemanticGraphSetModel.scope_type == "ontology",
            SemanticGraphSetModel.scope_id == question.ontology_id,
            SemanticGraphSetModel.status == "active",
            SemanticGraphSetMemberModel.role.in_(("asserted_ontology", "asserted_data")),
        )
    ).all()
    return [r[0] for r in rows]
```

Add the imports at the top of the file:

```python
from app.repositories.models import (
    SemanticGraphSetModel, SemanticGraphSetMemberModel,
)
```

`_question` already exists in the module.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && uv run pytest tests/test_interview_service.py::test_active_data_and_ontology_graphs_for_question_returns_member_iris -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/interview.py backend/tests/test_interview_service.py
git commit -m "feat(semantic): resolve active graph-set members for competency question"
```

---

### Task B3: Resolve Phase 2 IRI for class / relation IDs

**Files:**
- Modify: `backend/app/services/interview.py`
- Modify: `backend/tests/test_interview_service.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_resolve_class_iri_returns_phase2_mapping(in_memory_session):
    from app.services.interview import resolve_class_iri
    from app.repositories.models import OntologyModel, ProjectModel

    in_memory_session.add(ProjectModel(id="p-1", name="P"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.commit()

    iri = resolve_class_iri(in_memory_session, "o-1", "class-1")
    assert iri.startswith("http://ontology-platform.local/semantic/")
    assert "class-1" in iri or "class_1" in iri
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_interview_service.py::test_resolve_class_iri_returns_phase2_mapping -v
```

Expected: FAIL — function missing.

- [ ] **Step 3: Implement**

In `backend/app/services/interview.py`, add:

```python
def resolve_class_iri(session, ontology_id, class_id):
    """Return the RDF IRI for a class_id, using Phase 2 namespace mapping.

    Falls back to a stable, deterministic IRI if no mapping row exists. The
    Phase 2 mapping is the contract for legacy UUID → IRI translation.
    """
    from app.services.semantic_phase2_mapping import lookup_class_iri

    mapped = lookup_class_iri(session, ontology_id, class_id)
    if mapped:
        return mapped
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(class_id))
    return f"http://ontology-platform.local/semantic/ontology/{ontology_id}/class/{safe}"


def resolve_relation_type_iri(session, ontology_id, relation_type_id):
    from app.services.semantic_phase2_mapping import lookup_relation_type_iri

    mapped = lookup_relation_type_iri(session, ontology_id, relation_type_id)
    if mapped:
        return mapped
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(relation_type_id))
    return (
        f"http://ontology-platform.local/semantic/ontology/{ontology_id}"
        f"/relation/{safe}"
    )
```

If `semantic_phase2_mapping.py` does not exist, create it with the two lookup functions
returning `None` for now. Phase 2 mapping is pre-existing infrastructure (see
`docs/semantic/phase2-namespace-mapping-export.md`); if the names differ, grep for the
actual module: `grep -rnE "phase2|phase_2|iri_map" backend/app/services/`.

- [ ] **Step 4: Run to verify it passes**

```bash
cd backend && uv run pytest tests/test_interview_service.py::test_resolve_class_iri_returns_phase2_mapping -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/interview.py backend/app/services/semantic_phase2_mapping.py backend/tests/test_interview_service.py
git commit -m "feat(semantic): Phase 2 IRI resolver for competency question validate"
```

---

### Task B4: Rewrite `run_question_validation`

**Files:**
- Modify: `backend/app/services/interview.py`
- Modify: `backend/tests/test_interview_service.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_run_question_validation_entity_count_sparql_passes(in_memory_session, monkeypatch):
    from app.services import interview as svc

    in_memory_session.add(ProjectModel(id="p-1", name="P"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.add(CompetencyQuestionModel(
        id="q-1", project_id="p-1", ontology_id="o-1", question="q", position=0,
        status="testable",
        query_definition={"kind": "entity_count", "class_id": "class-1", "min_count": 1},
        source_brief_fields=[],
    ))
    in_memory_session.commit()

    monkeypatch.setattr(svc, "active_data_and_ontology_graphs_for_question",
                        lambda s, qid: ["https://x/g/data"])
    monkeypatch.setattr(svc, "resolve_class_iri",
                        lambda s, oid, cid: f"https://x/ont/{oid}/class/{cid}")

    class _Store:
        def query_sparql(self, query, timeout_seconds, limit):
            class _R:
                result = {"results": {"bindings": [{"count": {"value": "5"}}]}}
                result_format = "application/sparql-results+json"
            return _R()

    svc.run_question_validation(in_memory_session, _Store(), "q-1")
    question = in_memory_session.get(CompetencyQuestionModel, "q-1")
    assert question.status == "passed"
    assert question.validation_result["matches"] == 5


def test_run_question_validation_sparql_count_rejects_non_select(in_memory_session, monkeypatch):
    from app.services import interview as svc

    in_memory_session.add(ProjectModel(id="p-1", name="P"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.add(CompetencyQuestionModel(
        id="q-2", project_id="p-1", ontology_id="o-1", question="q", position=0,
        status="testable",
        query_definition={"kind": "sparql_count",
                          "sparql": "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
                          "expected_min": 1},
        source_brief_fields=[],
    ))
    in_memory_session.commit()

    monkeypatch.setattr(svc, "active_data_and_ontology_graphs_for_question",
                        lambda s, qid: ["https://x/g/data"])

    class _Store:
        def query_sparql(self, query, timeout_seconds, limit):
            raise AssertionError("should not reach the store")

    result = svc.run_question_validation(in_memory_session, _Store(), "q-2")
    assert result["status"] == "failed"
    assert "only SELECT allowed" in result["validation_result"]["error"]


def test_run_question_validation_sparql_count_passes(in_memory_session, monkeypatch):
    from app.services import interview as svc

    in_memory_session.add(ProjectModel(id="p-1", name="P"))
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O"))
    in_memory_session.add(CompetencyQuestionModel(
        id="q-3", project_id="p-1", ontology_id="o-1", question="q", position=0,
        status="testable",
        query_definition={"kind": "sparql_count",
                          "sparql": "SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } }",
                          "expected_min": 1, "expected_max": 100},
        source_brief_fields=[],
    ))
    in_memory_session.commit()

    monkeypatch.setattr(svc, "active_data_and_ontology_graphs_for_question",
                        lambda s, qid: ["https://x/g/data"])

    class _Store:
        def query_sparql(self, query, timeout_seconds, limit):
            class _R:
                result = {"results": {"bindings": [{"count": {"value": "42"}}]}}
                result_format = "application/sparql-results+json"
            return _R()

    result = svc.run_question_validation(in_memory_session, _Store(), "q-3")
    assert result["status"] == "passed"
    assert result["validation_result"]["matches"] == 42
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_interview_service.py -v -k "run_question_validation"
```

Expected: FAIL — `run_question_validation` still uses Neo4j.

- [ ] **Step 3: Rewrite `run_question_validation`**

Replace the body of `run_question_validation` in `backend/app/services/interview.py`:

```python
def run_question_validation(session, store, question_id):
    """Run the question's query definition as a SPARQL SELECT count over the
    active graph-set. Records pass/fail and validation_result.
    """
    from app.services.semantic_sparql_runner import SparqlGuardError, run_select_count

    question = _question(session, question_id)
    if question.status != "testable":
        raise HTTPException(status_code=409, detail="Only testable questions can be validated")
    definition = question.query_definition or {}
    kind = definition.get("kind")
    iris = active_data_and_ontology_graphs_for_question(session, question_id)

    try:
        if kind == "entity_count":
            class_iri = resolve_class_iri(session, question.ontology_id, definition.get("class_id"))
            query = (
                f"SELECT (COUNT(DISTINCT ?e) AS ?count) WHERE {{ "
                f"GRAPH ?g {{ ?e rdf:type/rdfs:subClassOf* <{class_iri}> }} }}"
            )
            count = run_select_count(
                store=store, query=query, graph_iris=iris,
                timeout_seconds=settings.competency_question_sparql_timeout_seconds,
            ).count
            expected_min = int(definition.get("min_count", 0))
            passed = count >= expected_min
        elif kind == "relation_count":
            predicate = resolve_relation_type_iri(
                session, question.ontology_id, definition.get("relation_type_id"),
            )
            query = (
                f"SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE {{ "
                f"GRAPH ?g {{ ?s <{predicate}> ?o }} }}"
            )
            count = run_select_count(
                store=store, query=query, graph_iris=iris,
                timeout_seconds=settings.competency_question_sparql_timeout_seconds,
            ).count
            expected_min = int(definition.get("min_count", 0))
            passed = count >= expected_min
        elif kind == "sparql_count":
            if "expected_min" not in definition and "expected_max" not in definition:
                raise HTTPException(
                    status_code=422,
                    detail="expected_min or expected_max required",
                )
            count = run_select_count(
                store=store, query=definition["sparql"], graph_iris=iris,
                timeout_seconds=settings.competency_question_sparql_timeout_seconds,
            ).count
            expected_min = definition.get("expected_min")
            expected_max = definition.get("expected_max")
            passed = True
            if expected_min is not None and count < expected_min:
                passed = False
            if expected_max is not None and count > expected_max:
                passed = False
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported query definition kind: {kind}",
            )
    except SparqlGuardError as exc:
        question.status = "failed"
        question.validation_result = {
            "kind": kind,
            "error": str(exc),
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
        session.commit()
        session.refresh(question)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SparqlQueryTimeout as exc:
        question.status = "failed"
        question.validation_result = {
            "kind": kind, "error": "sparql_timeout",
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
        session.commit()
        session.refresh(question)
        raise HTTPException(status_code=422, detail="sparql_timeout") from exc

    question.status = "passed" if passed else "failed"
    question.validation_result = {
        "kind": kind,
        "matches": count,
        "expected_min": expected_min if kind != "sparql_count" else definition.get("expected_min"),
        "expected_max": definition.get("expected_max") if kind == "sparql_count" else None,
        "passed": passed,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    session.commit()
    session.refresh(question)
    return {
        "status": question.status,
        "validation_result": question.validation_result,
    }
```

Add the imports at the top:

```python
import re
from app.core.config import Settings
from app.repositories.rdf_store import SparqlQueryTimeout
```

The route `validate_competency_question` in `backend/app/api/interview.py` already calls
`service.run_question_validation`. Update it to pass `settings`:

```python
@router.post("/competency-questions/{question_id}/validate", response_model=CompetencyQuestionRead)
def validate_competency_question(
    question_id: str,
    session: Session = Depends(get_db_session),
    rdf_store=Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    service.run_question_validation(session, rdf_store, question_id, settings)
    return session.get(CompetencyQuestionModel, question_id)
```

And update the service signature to accept `settings`:

```python
def run_question_validation(session, store, question_id, settings):
    ...
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_interview_service.py -v -k "run_question_validation"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/interview.py backend/app/api/interview.py backend/tests/test_interview_service.py
git commit -m "feat(semantic): reroute competency question validate to SPARQL"
```

---

### Task B5: Frontend `CompetencyQuestionsPage` editor update

**Files:**
- Modify: `frontend/src/pages/CompetencyQuestionsPage.tsx`

- [ ] **Step 1: Update the editor type**

Edit `frontend/src/pages/CompetencyQuestionsPage.tsx`. Replace the `EditorState` type with:

```typescript
type QueryDefinition =
  | { kind: "entity_count"; class_id: string; min_count: number }
  | { kind: "relation_count"; relation_type_id: string; min_count: number }
  | { kind: "sparql_count"; sparql: string; expected_min?: number; expected_max?: number };

type EditorState = {
  question: string;
  importance: number;
  queryDefinitionKind: "entity_count" | "relation_count" | "sparql_count";
  entityClassId: string;
  entityMinCount: number;
  relationTypeId: string;
  relationMinCount: number;
  sparql: string;
  sparqlExpectedMin?: number;
  sparqlExpectedMax?: number;
  sourceBriefFields: string[];
};

const emptyEditor: EditorState = {
  question: "", importance: 3,
  queryDefinitionKind: "entity_count",
  entityClassId: "", entityMinCount: 1,
  relationTypeId: "", relationMinCount: 1,
  sparql: "SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } }",
  sparqlExpectedMin: undefined, sparqlExpectedMax: undefined,
  sourceBriefFields: [],
};
```

- [ ] **Step 2: Update the save handler to serialize the right shape**

Replace `saveEditor` with:

```typescript
const saveEditor = async () => {
  if (!editing || !editor.question.trim()) return;
  let queryDefinition: QueryDefinition;
  if (editor.queryDefinitionKind === "entity_count") {
    queryDefinition = { kind: "entity_count", class_id: editor.entityClassId, min_count: editor.entityMinCount };
  } else if (editor.queryDefinitionKind === "relation_count") {
    queryDefinition = { kind: "relation_count", relation_type_id: editor.relationTypeId, min_count: editor.relationMinCount };
  } else {
    if (editor.sparqlExpectedMin === undefined && editor.sparqlExpectedMax === undefined) {
      setError(t("sparql_count 至少需要 expected_min 或 expected_max 之一"));
      return;
    }
    queryDefinition = {
      kind: "sparql_count",
      sparql: editor.sparql,
      expected_min: editor.sparqlExpectedMin,
      expected_max: editor.sparqlExpectedMax,
    };
  }

  const id = editing === "new" ? "new" : editing.id;
  await run(id, async () => {
    if (editing === "new") {
      return request<CompetencyQuestion>(`/projects/${projectId}/competency-questions`, {
        method: "POST",
        body: JSON.stringify({
          ontology_id: ontologyId, question: editor.question.trim(),
          importance: editor.importance,
          query_definition: queryDefinition,
          source_answer_ids: [], source_brief_fields: editor.sourceBriefFields,
        }),
      });
    }
    return request<CompetencyQuestion>(`/competency-questions/${editing.id}`, {
      method: "POST",  // legacy PATCH path stays; body is the same
      body: JSON.stringify({
        question: editor.question.trim(), importance: editor.importance,
        query_definition: queryDefinition, source_brief_fields: editor.sourceBriefFields,
      }),
    });
  }, editing === "new" ? t("能力问题已创建。") : t("能力问题已更新。"));
  setEditing(null);
};
```

Note: legacy `PATCH /competency-questions/{id}` stays. If the existing code uses
`PATCH`, keep `PATCH`.

- [ ] **Step 3: Replace the Modal form fields**

In the Modal, replace the existing `queryDefinition` JSON textarea with three
fieldsets gated by `editor.queryDefinitionKind`:

```tsx
<Select
  value={editor.queryDefinitionKind}
  onChange={(v) => setEditor((c) => ({ ...c, queryDefinitionKind: v }))}
  options={[
    { value: "entity_count", label: "entity_count" },
    { value: "relation_count", label: "relation_count" },
    { value: "sparql_count", label: "sparql_count" },
  ]}
/>
{editor.queryDefinitionKind === "entity_count" && (
  <>
    <label><span>{t("Class ID")}</span>
      <input value={editor.entityClassId} onChange={(e) => setEditor((c) => ({ ...c, entityClassId: e.target.value }))} />
    </label>
    <label><span>{t("最小数量")}</span>
      <input type="number" min={0} value={editor.entityMinCount}
        onChange={(e) => setEditor((c) => ({ ...c, entityMinCount: Number(e.target.value) }))} />
    </label>
  </>
)}
{editor.queryDefinitionKind === "relation_count" && (
  <>
    <label><span>{t("Relation Type ID")}</span>
      <input value={editor.relationTypeId} onChange={(e) => setEditor((c) => ({ ...c, relationTypeId: e.target.value }))} />
    </label>
    <label><span>{t("最小数量")}</span>
      <input type="number" min={0} value={editor.relationMinCount}
        onChange={(e) => setEditor((c) => ({ ...c, relationMinCount: Number(e.target.value) }))} />
    </label>
  </>
)}
{editor.queryDefinitionKind === "sparql_count" && (
  <>
    <label><span>{t("SPARQL SELECT")}</span>
      <textarea className="codeArea" rows={6} value={editor.sparql}
        placeholder={"SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ... } }"}
        onChange={(e) => setEditor((c) => ({ ...c, sparql: e.target.value }))} />
    </label>
    <label><span>{t("Expected min (可选)")}</span>
      <input type="number" value={editor.sparqlExpectedMin ?? ""}
        onChange={(e) => setEditor((c) => ({ ...c, sparqlExpectedMin: e.target.value === "" ? undefined : Number(e.target.value) }))} />
    </label>
    <label><span>{t("Expected max (可选)")}</span>
      <input type="number" value={editor.sparqlExpectedMax ?? ""}
        onChange={(e) => setEditor((c) => ({ ...c, sparqlExpectedMax: e.target.value === "" ? undefined : Number(e.target.value) }))} />
    </label>
  </>
)}
```

When opening the editor on an existing question, hydrate `editor` from the stored
`query_definition`:

```typescript
const q = question.query_definition as QueryDefinition;
const queryDefinitionKind = (q?.kind ?? "entity_count") as EditorState["queryDefinitionKind"];
setEditor({
  ...emptyEditor,
  question: question.question, importance: question.importance,
  queryDefinitionKind,
  entityClassId: q?.kind === "entity_count" ? q.class_id : "",
  entityMinCount: q?.kind === "entity_count" ? q.min_count : 1,
  relationTypeId: q?.kind === "relation_count" ? q.relation_type_id : "",
  relationMinCount: q?.kind === "relation_count" ? q.min_count : 1,
  sparql: q?.kind === "sparql_count" ? q.sparql : emptyEditor.sparql,
  sparqlExpectedMin: q?.kind === "sparql_count" ? q.expected_min : undefined,
  sparqlExpectedMax: q?.kind === "sparql_count" ? q.expected_max : undefined,
  sourceBriefFields: question.source_brief_fields,
});
```

- [ ] **Step 4: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CompetencyQuestionsPage.tsx
git commit -m "feat(frontend): competency question editor supports sparql_count"
```

---

## Track C — Smoke contract

### Task C1: Update semantic-language integration smoke entries

**Files:**
- Modify: `docs/semantic/semantic-language-integration-test-plan.md`

- [ ] **Step 1: Inspect the existing Stage 1 section**

```bash
grep -nE "Stage 1|Intake|build-context|competency-questions" docs/semantic/semantic-language-integration-test-plan.md
```

- [ ] **Step 2: Add the new smoke entries**

In the Stage 1 / Intake section, add:

```markdown
### Build Overview — graph-set read model

| Request | Expected |
| --- | --- |
| `GET /ontologies/{id}/build-overview?project={pid}` | 200 with `ontology_id`, `graph_set.members[*].role`, `graph_set.members[*].reasoning_stale`, `competency_questions.by_status`, `next_actions` |
| `GET /ontologies/{id}/build-overview` (no active graph-set) | 404 with detail mentioning "active graph-set" |
| `GET /graph-sets/{gs}/read-models/graph-set-staleness` | 200 envelope; `items[0].missing_evidence_count >= 0` |
| `GET /projects/{id}/build-context` (legacy) | `Deprecation: true` header present |

### Competency Question validate — SPARQL

| Request | Expected |
| --- | --- |
| `POST /competency-questions/{id}/validate` with `query_definition={kind:"entity_count", class_id:"...", min_count:1}` | 200, response body's `validation_result.matches` is an integer; `status` is `passed` or `failed` |
| Same with `kind:"relation_count"` | 200, same shape |
| Same with `kind:"sparql_count", sparql:"SELECT (COUNT(*) AS ?count) WHERE { GRAPH ?g { ?s ?p ?o } }", expected_min:0, expected_max:1000` | 200, `validation_result.matches` is an integer |
| Same with `sparql:"CONSTRUCT ..."` | 422 with `detail == "only SELECT allowed"` |
| Same with `sparql:"INSERT DATA ..."` | 422 with `detail == "only SELECT allowed"` |
```

- [ ] **Step 3: Commit**

```bash
git add docs/semantic/semantic-language-integration-test-plan.md
git commit -m "docs(semantic): add stage 1 smoke entries"
```

---

### Task C2: Backend integration smoke

**Files:**
- Modify: `backend/tests/test_semantic_api.py`

- [ ] **Step 1: Add the integration tests**

Append to `backend/tests/test_semantic_api.py`:

```python
def test_build_overview_smoke(client, ontology_with_graph_set):
    response = client.get(f"/ontologies/{ontology_with_graph_set}/build-overview?project=p-1")
    assert response.status_code == 200
    body = response.json()
    assert body["ontology_id"] == ontology_with_graph_set
    assert "members" in body["graph_set"]
    assert "next_actions" in body


def test_graph_set_staleness_read_model_smoke(client, ontology_with_graph_set):
    gs_id = client.get(f"/ontologies/{ontology_with_graph_set}/build-overview?project=p-1").json()["graph_set"]["graph_set_id"]
    response = client.get(f"/graph-sets/{gs_id}/read-models/graph-set-staleness")
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["model_name"] == "graph-set-staleness"
    assert "items" in envelope
```

The `ontology_with_graph_set` fixture must be added to `conftest.py` if it does not exist;
it should create a project, ontology, and an active graph-set with one ontology + one data
member graph.

- [ ] **Step 2: Run the smoke tests**

```bash
cd backend && uv run pytest tests/test_semantic_api.py -v -k "build_overview_smoke or staleness_read_model_smoke"
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_semantic_api.py backend/tests/conftest.py
git commit -m "test(semantic): add build-overview smoke"
```

---

## Self-Review

### Spec coverage

| Spec section | Plan task(s) |
| --- | --- |
| § 4.1 read-model template `graph-set-staleness` | A2, A3 |
| § 4.2 composer endpoint `/ontologies/{id}/build-overview` | A4, A5 |
| § 4.3 frontend rewrite | A7, A8, A9 |
| § 4.4 deprecation policy | A6 |
| § 5.1 query_definition schema | B5 |
| § 5.2 backend implementation (entity_count, relation_count, sparql_count) | B1, B2, B3, B4 |
| § 6 error/boundary | covered by tests in B1 and B4 |
| § 7 testing strategy | C1, C2 (smoke); unit tests in every task; Playwright in A9 |

No gaps.

### Placeholder scan

- § A3 references `_read_model_scope_resolver` and `ScopeResolution.members`. The plan
  calls these out explicitly and tells the engineer to extend `ScopeResolution` and mirror
  the existing `/graph-sets/{id}/read-models/{name}` wiring.
- § A5 references `brief_summary_for_overview` and `question_summary_for_overview` with
  the full implementation provided inline.
- § B3 references `semantic_phase2_mapping` with explicit fallback path.

No "TBD" / "implement later" / "similar to Task N" patterns.

### Type consistency

- `GraphSetMemberStaleness` fields (Python dataclass and TS type): `iri, role, editable,
  validation_stale, reasoning_stale, rule_stale, last_semantic_edit_at` — match across A3,
  A4, A7.
- `NextAction` fields: `key, label, detail, tab` — match across A4, A7, A8.
- `BuildOverviewResponse` fields: `ontology_id, graph_set, project_brief,
  competency_questions, next_actions` — match across A4, A7, A8.
- `QueryDefinition` discriminated union: `kind` strings `entity_count` / `relation_count`
  / `sparql_count` — match across B4 (backend) and B5 (frontend).
- `run_question_validation` signature: `(session, store, question_id, settings)` —
  matched in service definition (B4) and route call site (B4 step 3).

All consistent.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-06-semantic-stage1-intake.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
