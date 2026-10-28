"""Versioned candidate business records, separate from execution checkpoints and RDF."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .contracts import FrameworkError, digest


class WorkspaceRepository:
    def __init__(self, connection: dict, schema: str, task_ref: str):
        self.connection = connection
        self.schema = schema
        self.task_ref = task_ref

    def table(self, name: str) -> sql.Identifier:
        return sql.Identifier(self.schema, name)

    def connect(self, *, autocommit: bool = False):
        return psycopg.connect(**self.connection, autocommit=autocommit, row_factory=dict_row)

    def setup(self) -> None:
        with self.connect(autocommit=True) as conn:
            conn.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema))
            )
            conn.execute(
                sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    task_ref text NOT NULL, object_id text NOT NULL, kind text NOT NULL,
                    revision integer NOT NULL, content jsonb NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY(task_ref, object_id)
                )
            """).format(self.table("business_objects"))
            )
            conn.execute(
                sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    task_ref text NOT NULL, object_id text NOT NULL, kind text NOT NULL,
                    revision integer NOT NULL, base_revision integer NOT NULL,
                    content jsonb NOT NULL, operation_id text NOT NULL,
                    committed_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY(task_ref, object_id, revision), UNIQUE(task_ref, operation_id)
                )
            """).format(self.table("business_versions"))
            )

    @staticmethod
    def view(row: dict) -> dict:
        return {
            "object_id": row["object_id"],
            "kind": row["kind"],
            "revision": row["revision"],
            "content": row["content"],
            "authority": "candidate_workspace",
        }

    def get(self, object_id: str, revision: int | None = None) -> dict | None:
        with self.connect() as conn:
            query = sql.SQL("SELECT * FROM {} WHERE task_ref=%s AND object_id=%s")
            params = [self.task_ref, object_id]
            if revision is None:
                query = query.format(self.table("business_objects"))
            else:
                query = query.format(self.table("business_versions")) + sql.SQL(" AND revision=%s")
                params.append(revision)
            row = conn.execute(query, params).fetchone()
            return self.view(row) if row else None

    def put(
        self,
        object_id: str,
        kind: str,
        content: dict,
        expected_revision: int,
        *,
        operation_id: str | None = None,
    ) -> dict:
        intent = [self.task_ref, object_id, kind, expected_revision, content]
        operation_id = (
            operation_id
            or hashlib.sha256(
                json.dumps(intent, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
        )
        with self.connect() as conn:
            # Concurrent retries of this exact operation must see its committed
            # receipt. Different operations still use the revision comparison.
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                (self.task_ref, operation_id),
            )
            prior = conn.execute(
                sql.SQL("SELECT * FROM {} WHERE task_ref=%s AND operation_id=%s").format(
                    self.table("business_versions")
                ),
                (self.task_ref, operation_id),
            ).fetchone()
            if prior:
                if (
                    prior["object_id"],
                    prior["kind"],
                    prior["base_revision"],
                    prior["content"],
                ) != (
                    object_id,
                    kind,
                    expected_revision,
                    content,
                ):
                    return {
                        "code": "operation_conflict",
                        "recoverable": True,
                        "operation_id": operation_id,
                    }
                current = conn.execute(
                    sql.SQL("SELECT revision FROM {} WHERE task_ref=%s AND object_id=%s").format(
                        self.table("business_objects")
                    ),
                    (self.task_ref, object_id),
                ).fetchone()
                return {
                    "status": "recorded",
                    "replayed": True,
                    "operation_id": operation_id,
                    "object": self.view(prior),
                    "current_revision": current["revision"],
                }
            if expected_revision == 0:
                row = conn.execute(
                    sql.SQL("""
                    INSERT INTO {}(task_ref, object_id, kind, revision, content)
                    VALUES (%s,%s,%s,1,%s) ON CONFLICT DO NOTHING RETURNING *
                """).format(self.table("business_objects")),
                    (self.task_ref, object_id, kind, Jsonb(content)),
                ).fetchone()
            else:
                row = conn.execute(
                    sql.SQL("""
                    UPDATE {} SET revision=revision+1, kind=%s, content=%s, updated_at=now()
                    WHERE task_ref=%s AND object_id=%s AND revision=%s RETURNING *
                """).format(self.table("business_objects")),
                    (kind, Jsonb(content), self.task_ref, object_id, expected_revision),
                ).fetchone()
            if row is None:
                current = conn.execute(
                    sql.SQL("SELECT * FROM {} WHERE task_ref=%s AND object_id=%s").format(
                        self.table("business_objects")
                    ),
                    (self.task_ref, object_id),
                ).fetchone()
                baseline = conn.execute(
                    sql.SQL(
                        "SELECT content FROM {} WHERE task_ref=%s AND object_id=%s AND revision=%s"
                    ).format(self.table("business_versions")),
                    (self.task_ref, object_id, expected_revision),
                ).fetchone()
                old = baseline["content"] if baseline else {}
                actual = current["content"] if current else {}
                missing = object()
                return {
                    "code": "version_conflict",
                    "recoverable": True,
                    "expected_revision": expected_revision,
                    "actual": self.view(current) if current else None,
                    "changed_fields": sorted(
                        key
                        for key in old.keys() | actual.keys()
                        if old.get(key, missing) != actual.get(key, missing)
                    ),
                }
            conn.execute(
                sql.SQL("""
                INSERT INTO {}(task_ref,object_id,kind,revision,base_revision,content,operation_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """).format(self.table("business_versions")),
                (
                    self.task_ref,
                    object_id,
                    kind,
                    row["revision"],
                    expected_revision,
                    Jsonb(content),
                    operation_id,
                ),
            )
            return {
                "status": "recorded",
                "replayed": False,
                "operation_id": operation_id,
                "object": self.view(row),
                "current_revision": row["revision"],
            }

    @contextmanager
    def checkpointer(self, schema: str | None = None) -> Iterator[PostgresSaver]:
        namespace = schema or self.schema
        with self.connect(autocommit=True) as conn:
            conn.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(namespace))
            )
        # Quote the identifier; search_path must also work for Host-selected schema names.
        quoted = '"' + namespace.replace('"', '""') + '"'
        info = {**self.connection, "options": f"-csearch_path={quoted}"}
        with psycopg.connect(
            **info, autocommit=True, prepare_threshold=0, row_factory=dict_row
        ) as conn:
            saver = PostgresSaver(conn)
            saver.setup()
            yield saver

    def put_reference(
        self, object_id: str, kind: str, content: dict, expected_revision: int
    ) -> dict:
        result = self.put(object_id, kind, content, expected_revision)
        if result.get("status") != "recorded":
            raise FrameworkError(result["code"], actual=result)
        row = result["object"]
        return {
            "object_id": object_id,
            "revision": row["revision"],
            "digest": digest(row["content"]),
        }

    def read_reference(self, reference: dict) -> dict:
        row = self.get(reference["object_id"], reference["revision"])
        if row is None:
            raise FrameworkError("record_not_found", reference=reference)
        if digest(row["content"]) != reference["digest"]:
            raise FrameworkError("record_digest_mismatch", reference=reference)
        return row["content"]
