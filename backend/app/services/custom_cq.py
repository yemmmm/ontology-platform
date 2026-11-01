"""Project CQ definitions and fixed public snapshots; no model or SQL writes."""

import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.schemas import CustomCQDefinition
from app.repositories.models import CompetencyQuestionModel, ProjectModel


def content_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def is_custom(question):
    return (question.cq_definition or {}).get("kind") == "custom"


def _definition(value, actor):
    data = value.model_dump() if value is not None else CustomCQDefinition().model_dump()
    return {**data, "authored_by": actor}


def _new_question(session, project_id, payload, actor):
    if not payload.question.strip() or payload.query_definition:
        raise HTTPException(422, detail="Custom CQ requires a question and no count query")
    definition = _definition(payload.cq_definition, actor)
    position = payload.position
    if position is None:
        position = (
            int(
                session.scalar(
                    select(func.coalesce(func.max(CompetencyQuestionModel.position), -1)).where(
                        CompetencyQuestionModel.project_id == project_id
                    )
                )
                or 0
            )
            + 1
        )
    return CompetencyQuestionModel(
        id=str(uuid4()),
        project_id=project_id,
        ontology_id=payload.ontology_id,
        question=payload.question,
        importance=payload.importance,
        position=position,
        active=True,
        status="draft",
        content_revision=1,
        cq_definition=definition,
        external_id=definition["external_id"],
        query_definition={},
        validation_result={},
        source_answer_ids=payload.source_answer_ids,
        source_brief_fields=payload.source_brief_fields,
    )


def create_question(session, project_id, payload, actor=None):
    question = _new_question(session, project_id, payload, actor)
    session.add(question)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, detail={"code": "cq_external_id_conflict"}) from error
    session.refresh(question)
    return question


def update_question(session, question, payload, actor=None):
    # Re-read under the row lock: a stale ORM identity must not pass the revision comparison.
    question = session.scalar(
        select(CompetencyQuestionModel)
        .where(CompetencyQuestionModel.id == question.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if payload.expected_revision != question.content_revision:
        raise HTTPException(
            409,
            detail={
                "code": "cq_revision_conflict",
                "current_revision": question.content_revision,
                "question_id": question.id,
                "next_action": "reload_question",
            },
        )
    values = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if any(value is None for value in values.values()):
        raise HTTPException(422, detail="Custom CQ update fields cannot be null")
    if values.get("query_definition"):
        raise HTTPException(422, detail="Custom CQ does not use count queries")
    if "question" in values and not values["question"].strip():
        raise HTTPException(422, detail="Question must not be blank")
    if "cq_definition" in values:
        values["cq_definition"] = _definition(payload.cq_definition, actor)
        if values["cq_definition"]["external_id"] != question.external_id:
            raise HTTPException(422, detail="CQ external identity cannot be changed")
        if {**values["cq_definition"], "authored_by": None} == {
            **question.cq_definition,
            "authored_by": None,
        }:
            values["cq_definition"] = question.cq_definition
    changed = {key: value for key, value in values.items() if getattr(question, key) != value}
    if changed:
        for key, value in changed.items():
            setattr(question, key, value)
        question.content_revision += 1
        question.status = "draft"
        if question.validation_result:
            question.validation_result = {
                **question.validation_result,
                "stale": True,
                "reason": "question_edited",
            }
        session.commit()
        session.refresh(question)
    return question


def snapshot(session, project_id, question_ids=None):
    if session.get(ProjectModel, project_id) is None:
        raise HTTPException(404, detail="Project not found")
    rows = list(
        session.scalars(
            select(CompetencyQuestionModel)
            .where(
                CompetencyQuestionModel.project_id == project_id,
                CompetencyQuestionModel.active.is_(True),
            )
            .order_by(CompetencyQuestionModel.position, CompetencyQuestionModel.id)
        )
    )
    available = {row.id: row for row in rows if is_custom(row)}
    if question_ids is not None and set(question_ids) - available.keys():
        raise HTTPException(422, detail={"code": "cq_selection_unavailable"})
    selected = [
        row
        for row in available.values()
        if (
            row.id in question_ids
            if question_ids is not None
            else row.cq_definition.get("selected", True)
        )
    ]
    questions = []
    for row in selected:
        value = {
            "cq_id": row.id,
            "content_revision": row.content_revision,
            "question": row.question,
            "cq_definition": row.cq_definition,
            "active": row.active,
            "visibility": "public",
            "criteria_ready": row.cq_definition.get("criteria_status") == "confirmed",
        }
        questions.append({**value, "content_digest": content_digest(value)})
    value = {
        "schema_version": "ontoweave-cq-snapshot/v1",
        "project_id": project_id,
        "questions": questions,
    }
    sha256 = content_digest(value)
    return {**value, "snapshot_id": "cq-" + sha256[:24], "sha256": sha256}


def import_questions(session, project_id, payload, actor=None):
    from app.api.schemas import CompetencyQuestionCreate

    if (
        session.scalar(select(ProjectModel).where(ProjectModel.id == project_id).with_for_update())
        is None
    ):
        raise HTTPException(404, detail="Project not found")
    keys = [item.external_id for item in payload.questions]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, detail="Duplicate CQ external identities in import")
    rows, pending = [], []
    for item in payload.questions:
        definition = CustomCQDefinition(
            **item.model_dump(exclude={"question", "original_id"}),
            source_refs=payload.source_refs,
        )
        existing = session.scalar(
            select(CompetencyQuestionModel).where(
                CompetencyQuestionModel.project_id == project_id,
                CompetencyQuestionModel.external_id == item.external_id,
            )
        )
        if existing is not None:
            previous = {**existing.cq_definition, "authored_by": None}
            if existing.question != item.question or previous != definition.model_dump():
                raise HTTPException(
                    409,
                    detail={
                        "code": "cq_import_content_conflict",
                        "question_id": existing.id,
                        "external_id": item.external_id,
                        "current_revision": existing.content_revision,
                    },
                )
            rows.append(existing)
        else:
            row = _new_question(
                session,
                project_id,
                CompetencyQuestionCreate(question=item.question, cq_definition=definition),
                actor,
            )
            row.position += len(pending)
            pending.append(row)
            rows.append(row)
    session.add_all(pending)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def record_results(session, project_id, frozen, public, evaluation_id):
    """Host publishes validated public cases; private reports remain in their original run."""
    if frozen["project_id"] != project_id or public["cq_snapshot_id"] != frozen["snapshot_id"]:
        raise HTTPException(409, detail={"code": "cq_result_binding_mismatch"})
    by_id = {question["cq_id"]: question for question in frozen["questions"]}
    if {case["cq_id"] for case in public["custom_cq"]} != set(by_id):
        raise HTTPException(409, detail={"code": "cq_result_coverage_mismatch"})
    saved, stale = [], []
    for case in public["custom_cq"]:
        bound = by_id[case["cq_id"]]
        if any(case[key] != bound[key] for key in ("content_revision", "content_digest")):
            raise HTTPException(409, detail={"code": "cq_result_binding_mismatch"})
        row = session.scalar(
            select(CompetencyQuestionModel)
            .where(
                CompetencyQuestionModel.id == case["cq_id"],
                CompetencyQuestionModel.project_id == project_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.content_revision != case["content_revision"] or not row.active:
            stale.append(case["cq_id"])
            continue
        row.validation_result = {
            **{
                key: case[key]
                for key in (
                    "cq_id",
                    "content_revision",
                    "outcome",
                    "answerability",
                    "sql_readiness",
                    "sql_execution",
                )
            },
            "snapshot_id": frozen["snapshot_id"],
            "evaluation_id": evaluation_id,
            "model_revisions": public["model_revisions"],
            "stale": False,
        }
        saved.append(row.id)
    session.commit()
    return {"recorded": saved, "skipped_stale": stale}
