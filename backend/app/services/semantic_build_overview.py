"""Compose /ontologies/{id}/build-overview from Postgres + the Phase 6 read model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


class BuildOverviewService:
    def __init__(self, *, read_model, brief_summary, question_summary):
        self._read_model = read_model
        self._brief_summary = brief_summary
        self._question_summary = question_summary

    def build(self, *, session, project_id, ontology_id, graph_set_id):
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
    def _parse_graph_set(payload):
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
    def _derive_next_actions(graph_set, brief, questions):
        candidates = []
        if brief.completeness < 1.0:
            candidates.append(NextAction(
                key="complete_brief",
                label="完善 Project Brief",
                detail=f"{len(brief.missing_fields)} 个字段待处理",
                tab="brief",
            ))
        draft_count = questions.by_status.get("draft", 0)
        if draft_count > 0:
            candidates.append(NextAction(
                key="approve_questions",
                label="批准能力问题",
                detail=f"{draft_count} 个草稿待批准",
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
