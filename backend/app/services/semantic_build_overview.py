"""Compose /ontologies/{id}/build-overview from Postgres + the Phase 6 read model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OntologyModelState:
    ontology_id: str
    revision: int
    editable: bool


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
    model: OntologyModelState
    project_brief: BriefSummary
    competency_questions: CompetencyQuestionSummary
    next_actions: list[NextAction] = field(default_factory=list)


class BuildOverviewService:
    def __init__(self, *, read_model, brief_summary, question_summary):
        self._read_model = read_model
        self._brief_summary = brief_summary
        self._question_summary = question_summary

    def build(self, *, session, project_id, ontology_id):
        from app.repositories.models import OntologyModel
        ontology = session.get(OntologyModel, ontology_id)
        model = OntologyModelState(ontology_id, ontology.model_revision, True)

        brief = self._brief_summary(session, project_id)
        questions = self._question_summary(session, project_id)
        actions = self._derive_next_actions(model, brief, questions)

        return BuildOverviewResponse(
            ontology_id=ontology_id,
            model=model,
            project_brief=brief,
            competency_questions=questions,
            next_actions=actions,
        )


    @staticmethod
    def _derive_next_actions(model, brief, questions):
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
        return candidates[:3]
