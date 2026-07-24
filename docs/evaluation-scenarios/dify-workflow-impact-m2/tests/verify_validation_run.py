#!/usr/bin/env python3
"""Strictly read-only ORM verification of an M2 validation-run shape graph."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import event, select


ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.repositories.models import SemanticValidationRunModel  # noqa: E402
from app.repositories.postgres import create_session_factory  # noqa: E402


WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP", "TRUNCATE", "GRANT", "REVOKE")


def verify(run_id: str, expected_shape_graph_iri: str) -> dict[str, object]:
    """Read one persisted run and fail if SQLAlchemy attempts a write or DDL."""
    settings = Settings()
    factory = create_session_factory(settings)
    engine = factory.kw["bind"]

    @event.listens_for(engine, "before_cursor_execute")
    def reject_writes(_conn, _cursor, statement, _parameters, _context, _executemany):  # noqa: ANN001
        first = statement.lstrip().upper()
        if first.startswith(WRITE_PREFIXES):
            raise RuntimeError("read-only verifier rejected a SQL write/DDL statement")

    try:
        with factory() as session:
            row = session.execute(
                select(
                    SemanticValidationRunModel.id,
                    SemanticValidationRunModel.status,
                    SemanticValidationRunModel.conforms,
                    SemanticValidationRunModel.shape_graph_iris,
                ).where(SemanticValidationRunModel.id == run_id)
            ).one_or_none()
            if row is None:
                raise RuntimeError(f"validation run not found: {run_id}")
            if list(row.shape_graph_iris or []) != [expected_shape_graph_iri]:
                raise RuntimeError(
                    "shape_graph_iris did not exactly match expected Graph Set shapes member: "
                    f"{row.shape_graph_iris!r}"
                )
            if session.new or session.dirty or session.deleted:
                raise RuntimeError("read-only verifier unexpectedly has pending ORM writes")
            session.rollback()
            return {
                "run_id": row.id,
                "status": row.status,
                "conforms": row.conforms,
                "shape_graph_iris": list(row.shape_graph_iris or []),
                "read_only": True,
            }
    finally:
        event.remove(engine, "before_cursor_execute", reject_writes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-shape-graph-iri", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.run_id, args.expected_shape_graph_iri), ensure_ascii=False))
    except RuntimeError as exc:
        print(f"validation-run verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
