"""Relational feedback storage; original submissions are never updated."""

from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from app.repositories.models import SemanticFeedbackModel


class SemanticFeedbackRepository:
    def __init__(self, session):
        self.session = session

    def get(self, feedback_id, *, lock=False):
        statement = select(SemanticFeedbackModel).where(
            SemanticFeedbackModel.feedback_id == feedback_id
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def create(self, feedback_id, project_id, submitted_by, submission):
        existing = self.get(feedback_id)
        if existing:
            return existing
        row = SemanticFeedbackModel(
            feedback_id=feedback_id,
            project_id=project_id,
            submitted_by=submitted_by,
            submission=submission,
            created_at=datetime.now(UTC),
            resolution_history=[],
            outcome="pending",
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.get(feedback_id)
            if existing is None:
                raise
            return existing
        self.session.refresh(row)
        return row

    def list(self, project_id, pending_only, limit, after):
        model = SemanticFeedbackModel
        statement = select(model).where(model.project_id == project_id)
        if pending_only:
            statement = statement.where(
                model.outcome.in_(["pending", "unresolved", "needs_clarification"])
            )
        if after:
            stamp, fid = after
            statement = statement.where(
                or_(
                    model.created_at > stamp,
                    and_(model.created_at == stamp, model.feedback_id > fid),
                )
            )
        return list(
            self.session.scalars(
                statement.order_by(model.created_at, model.feedback_id).limit(limit)
            )
        )

    def append_resolution(self, row, resolution):
        row.resolution_history = [*row.resolution_history, resolution]
        row.outcome = resolution["outcome"]
        self.session.commit()
