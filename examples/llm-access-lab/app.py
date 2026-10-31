"""Standalone, constructed business fixture; no external LLM calls."""

import argparse
import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelInput(Input):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    quota_cost: int = Field(default=1, ge=1, strict=True)


class EnabledInput(Input):
    enabled: bool


class QuotaCostInput(Input):
    quota_cost: int = Field(ge=1, strict=True)


class KeyInput(Input):
    name: str = Field(min_length=1, max_length=100)
    allowed_models: list[str] = Field(min_length=1)
    quota: int = Field(ge=0, strict=True)


class CallInput(Input):
    request_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=4000)


def create_app(database_path: str | Path) -> FastAPI:
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def database():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    with database() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS models (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL,
                quota_cost INTEGER NOT NULL DEFAULT 1 CHECK (quota_cost >= 1)
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
                enabled INTEGER NOT NULL, remaining_quota INTEGER NOT NULL
                    CHECK (remaining_quota >= 0)
            );
            CREATE TABLE IF NOT EXISTS model_grants (
                key_id TEXT NOT NULL REFERENCES api_keys(id),
                model_id TEXT NOT NULL REFERENCES models(id),
                PRIMARY KEY (key_id, model_id)
            );
            CREATE TABLE IF NOT EXISTS calls (
                id TEXT PRIMARY KEY, key_id TEXT NOT NULL REFERENCES api_keys(id),
                request_id TEXT NOT NULL, model_id TEXT NOT NULL REFERENCES models(id),
                prompt TEXT NOT NULL, reply TEXT NOT NULL, charged_units INTEGER NOT NULL,
                created_at TEXT NOT NULL, UNIQUE (key_id, request_id)
            );
        """)
        if "quota_cost" not in {
            row["name"] for row in connection.execute("PRAGMA table_info(models)")
        }:
            connection.execute(
                "ALTER TABLE models ADD COLUMN quota_cost INTEGER NOT NULL DEFAULT 1 "
                "CHECK (quota_cost >= 1)"
            )

    app = FastAPI(
        title="模型访问与额度管理测试系统",
        version="0.2.0",
        description="构造业务：本机管理 API、测试调用凭证和模型扣额单位；响应由本地生成。",
    )

    def read_key(connection, key_id):
        row = connection.execute(
            "SELECT id, name, enabled, remaining_quota FROM api_keys WHERE id = ?", (key_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "key_not_found")
        grants = connection.execute(
            "SELECT model_id FROM model_grants WHERE key_id = ? ORDER BY model_id", (key_id,)
        ).fetchall()
        return {
            **dict(row),
            "enabled": bool(row["enabled"]),
            "allowed_models": [grant["model_id"] for grant in grants],
        }

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/admin/models", status_code=201)
    def create_model(data: ModelInput):
        with database() as connection:
            try:
                connection.execute(
                    "INSERT INTO models (id, name, enabled, quota_cost) VALUES (?, ?, ?, ?)",
                    (data.id, data.name, data.enabled, data.quota_cost),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "model_already_exists") from None
        return data.model_dump()

    @app.get("/admin/models")
    def list_models():
        with database() as connection:
            return [
                {**dict(row), "enabled": bool(row["enabled"])}
                for row in connection.execute("SELECT * FROM models ORDER BY id").fetchall()
            ]

    @app.patch("/admin/models/{model_id}")
    def set_model_enabled(model_id: str, data: EnabledInput):
        with database() as connection:
            changed = connection.execute(
                "UPDATE models SET enabled = ? WHERE id = ?", (data.enabled, model_id)
            )
            if not changed.rowcount:
                raise HTTPException(404, "model_not_found")
            row = connection.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
            return {**dict(row), "enabled": bool(row["enabled"])}

    @app.post("/admin/keys", status_code=201)
    def create_key(data: KeyInput):
        key_id, token = uuid4().hex, secrets.token_urlsafe(24)
        with database() as connection:
            for model_id in set(data.allowed_models):
                if not connection.execute(
                    "SELECT 1 FROM models WHERE id = ?", (model_id,)
                ).fetchone():
                    raise HTTPException(400, "unknown_model_in_grant")
            connection.execute(
                "INSERT INTO api_keys VALUES (?, ?, ?, ?, ?)",
                (key_id, data.name, hashlib.sha256(token.encode()).hexdigest(), True, data.quota),
            )
            connection.executemany(
                "INSERT INTO model_grants VALUES (?, ?)",
                [(key_id, model_id) for model_id in sorted(set(data.allowed_models))],
            )
            return {**read_key(connection, key_id), "token": token}

    @app.patch("/admin/models/{model_id}/quota-cost")
    def set_model_quota_cost(model_id: str, data: QuotaCostInput):
        with database() as connection:
            changed = connection.execute(
                "UPDATE models SET quota_cost = ? WHERE id = ?", (data.quota_cost, model_id)
            )
            if not changed.rowcount:
                raise HTTPException(404, "model_not_found")
            row = connection.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
            return {**dict(row), "enabled": bool(row["enabled"])}

    @app.get("/admin/keys")
    def list_keys():
        with database() as connection:
            return [
                read_key(connection, row["id"])
                for row in connection.execute("SELECT id FROM api_keys ORDER BY id").fetchall()
            ]

    @app.get("/admin/keys/{key_id}")
    def get_key(key_id: str):
        with database() as connection:
            return read_key(connection, key_id)

    @app.patch("/admin/keys/{key_id}")
    def set_key_enabled(key_id: str, data: EnabledInput):
        with database() as connection:
            changed = connection.execute(
                "UPDATE api_keys SET enabled = ? WHERE id = ?", (data.enabled, key_id)
            )
            if not changed.rowcount:
                raise HTTPException(404, "key_not_found")
            return read_key(connection, key_id)

    @app.get("/admin/calls")
    def list_calls():
        with database() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM calls ORDER BY created_at, id"
                ).fetchall()
            ]

    def receipt(row, remaining_quota, replayed):
        return {
            "call_id": row["id"],
            "model_id": row["model_id"],
            "reply": row["reply"],
            "charged_units": 0 if replayed else row["charged_units"],
            "remaining_quota": remaining_quota,
            "replayed": replayed,
        }

    @app.post("/calls")
    def make_call(data: CallInput, authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "invalid_credential")
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with database() as connection:
            # Serialize the check, debit and receipt across concurrent HTTP requests.
            connection.execute("BEGIN IMMEDIATE")
            key_row = connection.execute(
                "SELECT * FROM api_keys WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if key_row is None:
                raise HTTPException(401, "invalid_credential")
            if not key_row["enabled"]:
                raise HTTPException(403, "key_disabled")
            existing = connection.execute(
                "SELECT * FROM calls WHERE key_id = ? AND request_id = ?",
                (key_row["id"], data.request_id),
            ).fetchone()
            if existing:
                if existing["model_id"] != data.model_id or existing["prompt"] != data.prompt:
                    raise HTTPException(409, "request_id_conflict")
                return receipt(existing, key_row["remaining_quota"], True)
            model_row = connection.execute(
                "SELECT * FROM models WHERE id = ?", (data.model_id,)
            ).fetchone()
            if model_row is None:
                raise HTTPException(404, "model_not_found")
            if not connection.execute(
                "SELECT 1 FROM model_grants WHERE key_id = ? AND model_id = ?",
                (key_row["id"], data.model_id),
            ).fetchone():
                raise HTTPException(403, "model_not_allowed")
            if not model_row["enabled"]:
                raise HTTPException(409, "model_disabled")
            cost = model_row["quota_cost"]
            if key_row["remaining_quota"] < cost:
                raise HTTPException(429, "quota_exhausted")
            row = {
                "id": uuid4().hex,
                "key_id": key_row["id"],
                "request_id": data.request_id,
                "model_id": data.model_id,
                "prompt": data.prompt,
                "reply": f"{data.model_id}: {data.prompt}",
                "charged_units": cost,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            connection.execute(
                "UPDATE api_keys SET remaining_quota = remaining_quota - ? WHERE id = ?",
                (cost, key_row["id"]),
            )
            connection.execute(
                "INSERT INTO calls VALUES (:id, :key_id, :request_id, :model_id, :prompt, "
                ":reply, :charged_units, :created_at)",
                row,
            )
            return receipt(row, key_row["remaining_quota"] - cost, False)

    return app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Run the local modeling fixture")
    parser.add_argument("--db", default="data/lab.sqlite")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)
