from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from neo4j import Driver
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    CompetencyQuestionCreate,
    CompetencyQuestionStatusUpdate,
    CompetencyQuestionUpdate,
    InterviewAnswerCreate,
    ProjectBriefUpdate,
)
from app.repositories.models import (
    CompetencyQuestionModel,
    InterviewAnswerModel,
    OntologyModel,
    OntologyVersionModel,
    ProjectBriefModel,
    ProjectModel,
)
from app.services.semantic_build_overview import BriefSummary, CompetencyQuestionSummary

BRIEF_FIELDS = (
    "domain_name",
    "business_goal",
    "scope",
    "core_concepts",
    "identity_rules",
    "expected_granularity",
    "data_sources",
    "boundaries",
    "terminology",
    "inference_scope",
)
REQUIRED_FIELDS = BRIEF_FIELDS[:6]
FIELD_PROMPTS = {
    "domain_name": "What business domain should this ontology describe?",
    "business_goal": "What business outcome should the knowledge graph support?",
    "scope": "What is in scope and explicitly out of scope?",
    "core_concepts": "What are the core concepts, events, and participants?",
    "identity_rules": "Which identity keys and lifecycle rules distinguish entities?",
    "expected_granularity": "What level of detail should entities and facts use?",
    "data_sources": "Which sources are available and which are most trustworthy?",
    "boundaries": "What time, geography, or version boundaries apply?",
    "terminology": "Which domain terms, aliases, and languages matter?",
    "inference_scope": "Which inferences may the platform make?",
}
SKIP_IMPACTS = {
    "data_sources": "Evidence ranking and extraction confidence will be less reliable.",
    "boundaries": "Generated concepts and facts may exceed the intended context.",
    "terminology": "Alias matching and entity resolution quality may decrease.",
    "inference_scope": "The system must use conservative inference defaults.",
}
QUESTION_TRANSITIONS = {
    "draft": {"approved"},
    "approved": {"testable"},
    "testable": {"passed", "failed"},
    "passed": {"testable"},
    "failed": {"testable"},
}


def _id() -> str:
    return str(uuid4())


def _nonempty(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def assess_brief(
    content: dict[str, Any], field_states: dict[str, str], field_sources: dict[str, list[str]]
) -> dict[str, Any]:
    missing = [
        key
        for key in BRIEF_FIELDS
        if not _nonempty(content.get(key)) and field_states.get(key) != "skipped"
    ]
    clarification: list[dict[str, str]] = []
    for key in BRIEF_FIELDS:
        state = field_states.get(key)
        if key in missing:
            clarification.append({"field": key, "question": FIELD_PROMPTS[key], "reason": "missing"})
        elif _nonempty(content.get(key)) and state != "confirmed":
            clarification.append(
                {"field": key, "question": f"Please confirm the {key.replace('_', ' ')}.", "reason": "unconfirmed"}
            )
    skipped = [key for key in BRIEF_FIELDS if field_states.get(key) == "skipped"]
    for key in skipped:
        clarification.append(
            {"field": key, "question": "Skipped", "reason": SKIP_IMPACTS.get(key, "Quality may decrease.")}
        )
    resolved = sum(
        1
        for key in BRIEF_FIELDS
        if field_states.get(key) in {"confirmed", "skipped"} and (key not in REQUIRED_FIELDS or _nonempty(content.get(key)))
    )
    return {
        "fields": content,
        "field_states": field_states,
        "field_sources": field_sources,
        "missing_fields": missing,
        # A conversational turn asks at most three high-value questions. Skipped fields are
        # included only as impact notices and never asked again.
        "clarification_items": clarification[:3],
        "completeness": round(resolved / len(BRIEF_FIELDS), 3),
    }


def _project(session: Session, project_id: str) -> ProjectModel:
    project = session.get(ProjectModel, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_project_brief(session: Session, project_id: str) -> dict[str, Any]:
    _project(session, project_id)
    brief = session.scalar(select(ProjectBriefModel).where(ProjectBriefModel.project_id == project_id))
    result = assess_brief(
        brief.content if brief else {}, brief.field_states if brief else {}, brief.field_sources if brief else {}
    )
    return {"id": brief.id if brief else None, "project_id": project_id, **result}


def get_build_context(session: Session, project_id: str) -> dict[str, Any]:
    project = _project(session, project_id)
    ontologies = list(
        session.scalars(
            select(OntologyModel)
            .where(OntologyModel.project_id == project_id)
            .order_by(OntologyModel.created_at)
        )
    )
    questions = list_questions(session, project_id, include_inactive=True)
    version_ids = [ontology.current_version_id for ontology in ontologies if ontology.current_version_id]
    versions = {
        version.id: version
        for version in session.scalars(
            select(OntologyVersionModel).where(OntologyVersionModel.id.in_(version_ids))
        )
    }
    question_counts: dict[str, int] = {}
    for question in questions:
        key = "inactive" if not question.active else question.status
        question_counts[key] = question_counts.get(key, 0) + 1
    return {
        "project": {"id": project.id, "name": project.name, "description": project.description},
        "project_brief": get_project_brief(session, project_id),
        "ontologies": [
            {
                "id": ontology.id,
                "name": ontology.name,
                "status": ontology.status,
                "current_version_id": ontology.current_version_id,
                "current_version": (
                    {
                        "status": versions[ontology.current_version_id].status,
                        "workflow_status": versions[ontology.current_version_id].workflow_status,
                        "version_number": versions[ontology.current_version_id].version_number,
                    }
                    if ontology.current_version_id in versions
                    else None
                ),
            }
            for ontology in ontologies
        ],
        "competency_question_counts": question_counts,
    }


def create_answer(
    session: Session, project_id: str, payload: InterviewAnswerCreate
) -> InterviewAnswerModel:
    _project(session, project_id)
    answer = InterviewAnswerModel(id=_id(), project_id=project_id, **payload.model_dump())
    session.add(answer)
    session.commit()
    session.refresh(answer)
    return answer


def _validate_answer_ids(session: Session, project_id: str, answer_ids: set[str]) -> None:
    if not answer_ids:
        return
    found = set(
        session.scalars(
            select(InterviewAnswerModel.id).where(
                InterviewAnswerModel.project_id == project_id, InterviewAnswerModel.id.in_(answer_ids)
            )
        )
    )
    if found != answer_ids:
        raise HTTPException(status_code=400, detail="Answer sources must belong to the project")


def update_project_brief(
    session: Session, project_id: str, payload: ProjectBriefUpdate
) -> dict[str, Any]:
    _project(session, project_id)
    unknown = (
        set(payload.fields)
        | set(payload.confirmed_fields)
        | set(payload.skipped_fields)
        | set(payload.source_answer_ids)
    ) - set(BRIEF_FIELDS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown Project Brief fields: {sorted(unknown)}")
    illegal_skips = set(payload.skipped_fields) & set(REQUIRED_FIELDS)
    if illegal_skips:
        raise HTTPException(status_code=422, detail=f"Required fields cannot be skipped: {sorted(illegal_skips)}")
    source_ids = {item for values in payload.source_answer_ids.values() for item in values}
    _validate_answer_ids(session, project_id, source_ids)
    brief = session.scalar(select(ProjectBriefModel).where(ProjectBriefModel.project_id == project_id))
    if brief is None:
        brief = ProjectBriefModel(id=_id(), project_id=project_id, content={}, field_states={}, field_sources={})
        session.add(brief)
    old_content = dict(brief.content)
    old_sources = {key: list(value) for key, value in brief.field_sources.items()}
    content = {**brief.content, **payload.fields}
    states = dict(brief.field_states)
    sources = {key: list(value) for key, value in brief.field_sources.items()}
    for key in payload.fields:
        states[key] = "unconfirmed"
    for key in payload.confirmed_fields:
        if not _nonempty(content.get(key)):
            raise HTTPException(status_code=422, detail=f"Cannot confirm empty field: {key}")
        states[key] = "confirmed"
    for key in payload.skipped_fields:
        states[key] = "skipped"
        content.pop(key, None)
    sources.update(payload.source_answer_ids)
    changed = {
        key for key in set(payload.fields) | set(payload.source_answer_ids)
        if old_content.get(key) != content.get(key) or old_sources.get(key, []) != sources.get(key, [])
    }
    brief.content, brief.field_states, brief.field_sources = content, states, sources
    if changed:
        questions = session.scalars(
            select(CompetencyQuestionModel).where(CompetencyQuestionModel.project_id == project_id)
        )
        invalidate_questions_for_brief_change(questions, changed)
    session.commit()
    session.refresh(brief)
    return {"id": brief.id, "project_id": project_id, **assess_brief(content, states, sources)}


def invalidate_questions_for_brief_change(
    questions: Any, changed_fields: set[str]
) -> None:
    for question in questions:
        affected = changed_fields.intersection(question.source_brief_fields)
        if affected and question.status in {"testable", "passed", "failed"}:
            question.status = "approved"
            question.validation_result = {
                **question.validation_result,
                "stale": True,
                "reason": "source_project_brief_changed",
                "changed_fields": sorted(affected),
            }


def invalidate_questions_for_graph_change(
    questions: Any, changed_entity_ids: set[str]
) -> int:
    """Knock validated questions back to testable when their evidence graph changes."""
    if not changed_entity_ids:
        return 0
    affected = 0
    for question in questions:
        if question.status not in {"passed", "failed"}:
            continue
        previous = question.validation_result or {}
        if not previous:
            continue
        question.status = "testable"
        question.validation_result = {
            **previous,
            "stale": True,
            "reason": "graph_data_changed",
            "changed_entity_ids": sorted(changed_entity_ids),
        }
        affected += 1
    return affected


def list_questions(session: Session, project_id: str, include_inactive: bool = False) -> list[CompetencyQuestionModel]:
    _project(session, project_id)
    query = select(CompetencyQuestionModel).where(CompetencyQuestionModel.project_id == project_id)
    if not include_inactive:
        query = query.where(CompetencyQuestionModel.active.is_(True))
    return list(session.scalars(query.order_by(CompetencyQuestionModel.position, CompetencyQuestionModel.created_at)))


def create_question(
    session: Session, project_id: str, payload: CompetencyQuestionCreate
) -> CompetencyQuestionModel:
    _project(session, project_id)
    ontology = session.get(OntologyModel, payload.ontology_id)
    if ontology is None or ontology.project_id != project_id:
        raise HTTPException(status_code=400, detail="Ontology must belong to the project")
    _validate_answer_ids(session, project_id, set(payload.source_answer_ids))
    unknown = set(payload.source_brief_fields) - set(BRIEF_FIELDS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown source brief fields: {sorted(unknown)}")
    position = payload.position
    if position is None:
        maximum = session.scalar(
            select(func.coalesce(func.max(CompetencyQuestionModel.position), -1)).where(
                CompetencyQuestionModel.project_id == project_id
            )
        )
        position = int(maximum if maximum is not None else -1) + 1
    question = CompetencyQuestionModel(
        id=_id(), project_id=project_id, status="draft", active=True,
        **payload.model_dump(exclude={"position"}), position=position,
    )
    session.add(question)
    session.commit()
    session.refresh(question)
    return question


def _question(session: Session, question_id: str) -> CompetencyQuestionModel:
    question = session.get(CompetencyQuestionModel, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Competency question not found")
    return question


def update_question(
    session: Session, question_id: str, payload: CompetencyQuestionUpdate
) -> CompetencyQuestionModel:
    question = _question(session, question_id)
    values = payload.model_dump(exclude_unset=True)
    if "source_answer_ids" in values:
        _validate_answer_ids(session, question.project_id, set(values["source_answer_ids"]))
    if "source_brief_fields" in values:
        unknown = set(values["source_brief_fields"]) - set(BRIEF_FIELDS)
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown source brief fields: {sorted(unknown)}")
    substantive = set(values) - {"position", "active"}
    for key, value in values.items():
        setattr(question, key, value)
    if substantive and question.status != "draft":
        question.status = "draft"
        question.validation_result = {"stale": True, "reason": "question_edited"}
    session.commit()
    session.refresh(question)
    return question


def set_question_status(
    session: Session, question_id: str, payload: CompetencyQuestionStatusUpdate
) -> CompetencyQuestionModel:
    question = _question(session, question_id)
    if not question.active:
        raise HTTPException(status_code=409, detail="Inactive competency questions cannot transition")
    if payload.status not in QUESTION_TRANSITIONS.get(question.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid question transition: {question.status} -> {payload.status}")
    if payload.status == "approved" and not (question.source_answer_ids or question.source_brief_fields):
        raise HTTPException(status_code=422, detail="Approved questions require an answer or Project Brief source")
    if payload.status == "approved" and question.source_brief_fields:
        brief = session.scalar(
            select(ProjectBriefModel).where(ProjectBriefModel.project_id == question.project_id)
        )
        invalid_fields = [
            key
            for key in question.source_brief_fields
            if brief is None
            or not _nonempty(brief.content.get(key))
            or brief.field_states.get(key) != "confirmed"
        ]
        if invalid_fields:
            raise HTTPException(
                status_code=422,
                detail=f"Question sources must be confirmed Project Brief fields: {invalid_fields}",
            )
    if payload.status == "testable" and not question.query_definition:
        raise HTTPException(status_code=422, detail="A query definition is required before testing")
    if payload.status in {"passed", "failed"} and not payload.validation_result:
        raise HTTPException(status_code=422, detail="A validation result is required")
    question.status = payload.status
    question.validation_result = payload.validation_result
    session.commit()
    session.refresh(question)
    return question


def run_question_validation(
    session: Session, driver: Driver, question_id: str
) -> dict[str, Any]:
    """Run the question's bound query definition and record pass/fail."""
    question = _question(session, question_id)
    if question.status != "testable":
        raise HTTPException(status_code=409, detail="Only testable questions can be validated")
    definition = question.query_definition or {}
    kind = definition.get("kind")
    if kind == "entity_count":
        class_id = definition.get("class_id")
        if not class_id:
            raise HTTPException(status_code=422, detail="entity_count query requires class_id")
        query = """
        MATCH (entity:Entity {ontology_id: $ontology_id, class_id: $class_id})
        RETURN count(entity) AS count
        """
        params = {"ontology_id": question.ontology_id, "class_id": class_id}
    elif kind == "relation_count":
        rt_id = definition.get("relation_type_id")
        if not rt_id:
            raise HTTPException(status_code=422, detail="relation_count query requires relation_type_id")
        query = """
        MATCH ()-[relation {ontology_id: $ontology_id, relation_type_id: $rt_id}]->()
        RETURN count(relation) AS count
        """
        params = {"ontology_id": question.ontology_id, "rt_id": rt_id}
    else:
        raise HTTPException(
            status_code=422, detail=f"Unsupported query definition kind: {kind}"
        )
    with driver.session() as graph_session:
        record = graph_session.run(query, **params).single()
    matches = int((record or {}).get("count", 0)) if isinstance(record, dict) else int(record["count"])
    expected_min = int(definition.get("min_count", 0))
    passed = matches >= expected_min
    result = {
        "matches": matches,
        "expected_min": expected_min,
        "passed": passed,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    question.status = "passed" if passed else "failed"
    question.validation_result = result
    session.commit()
    session.refresh(question)
    return result


def brief_summary_for_overview(session, project_id):
    """Return BriefSummary for the build-overview composer."""
    brief = session.scalar(
        select(ProjectBriefModel).where(ProjectBriefModel.project_id == project_id)
    )
    if not brief:
        return BriefSummary(completeness=0.0, missing_fields=[])
    content = brief.content or {}
    states = brief.field_states or {}
    # All expected brief fields
    brief_fields = [
        "domain_name", "business_goal", "scope", "core_concepts",
        "identity_rules", "expected_granularity", "data_sources",
        "boundaries", "terminology", "inference_scope",
    ]
    missing = [k for k, v in states.items() if v != "confirmed"]
    missing += [k for k in brief_fields if k not in content and k not in missing]
    completeness = 1.0 - (len(missing) / len(brief_fields)) if brief_fields else 0.0
    return BriefSummary(
        completeness=max(0.0, completeness),
        missing_fields=missing,
    )


def question_summary_for_overview(session, project_id):
    """Return CompetencyQuestionSummary for the build-overview composer."""
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
