#!/usr/bin/env python3
"""Minimal external SQL execution adapter for R3.0-005 (platform-external tool).

Contract (docs/delivery/designs/2026-08-27-r3-0-005-ontology-guided-sql-qa-design.md §3.2):

- Input: exactly one JSON object on stdin, ``{"sql": "<single SQL statement>"}``.
  Anything else (non-JSON, non-object, unknown keys, non-string ``sql``, empty
  payload, multiple statements) is rejected as ``input_error`` (fail-closed).
  SQL is never read from command-line arguments.
- Output: exactly one JSON object on stdout.
  - success: ``{"ok": true, "columns": [...], "rows": [[...], ...]}``
  - failure: ``{"ok": false, "error": {"kind": <kind>, "message": <text>}}``
    where ``kind`` is one of ``config_error`` / ``input_error`` /
    ``database_error``.
- Result serialization uses one frozen minimal conversion set:
  NULL/bool/int/float stay native JSON; numeric/decimal values become decimal
  strings; date/time/timestamp/timestamptz/interval/UUID values become stable
  ISO/canonical strings; any other type falls back to ``str()``. No locale
  formatting, no rounding, no type inference beyond this set.
- Exit code: 0 when ``ok`` is true, 1 when ``ok`` is false. stderr carries only
  short diagnostic text, never a traceback.
- Connection: the DSN comes only from the environment variable
  ``R3005_SQL_ADAPTER_DSN``; a missing or unparsable DSN is ``config_error``.
  The connection is opened with ``options=-c default_transaction_read_only=on``
  so PostgreSQL rejects write transactions (INSERT/UPDATE/DELETE/DDL/WRITE
  CTEs) with a read-only transaction error surfaced as ``database_error``.
- One statement per invocation. No retries, no caching, no pooling, no dialect
  adapters (PostgreSQL only).

PRODUCTION REPLACEMENT BOUNDARY (requirement R3.0-005, mandatory statement):
before entering a real production environment this adapter must be replaced or
wrapped by an external data-security boundary that enforces user-ID, tenant,
organization, and row/column-level policies (Business Data Authorization).
Acceptance evidence produced with this adapter MUST NOT be interpreted as
business-data security being established.

This adapter is NOT a policy engine: it performs no authorization decisions,
no SQL rewriting, no semantic validation, no auditing, and no row/column
filtering. It executes one supplied statement against one read-only connection
and returns what the database returns.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import uuid
from decimal import Decimal

DSN_ENV = "R3005_SQL_ADAPTER_DSN"
READ_ONLY_OPTIONS = "-c default_transaction_read_only=on"


def _fail(kind: str, message: str) -> int:
    json.dump(
        {"ok": False, "error": {"kind": kind, "message": message}},
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 1


def _statement_is_single(sql: str) -> bool:
    """Reject multi-statement payloads and empty payloads.

    A small scanner tracks quoting context (single-quoted strings, double-quoted
    identifiers, dollar-quoted blocks, ``--`` and ``/* */`` comments) and counts
    top-level semicolons. Exactly one statement is allowed and nothing but
    whitespace/comments may follow its terminator.
    """
    semicolons = 0
    saw_code = False
    trailing_code = False
    position = 0
    length = len(sql)
    while position < length:
        char = sql[position]
        if char == "'":
            saw_code = True
            trailing_code = trailing_code or semicolons > 0
            position += 1
            while position < length:
                if sql[position] == "'":
                    if position + 1 < length and sql[position + 1] == "'":
                        position += 2
                        continue
                    break
                position += 1
            position += 1
            continue
        if char == '"':
            saw_code = True
            trailing_code = trailing_code or semicolons > 0
            position += 1
            while position < length and sql[position] != '"':
                position += 1
            position += 1
            continue
        if char == "$":
            end = sql.find("$", position + 1)
            tag = sql[position : end + 1] if end != -1 else ""
            if tag.startswith("$") and len(tag) > 2 and tag[1].isalpha():
                saw_code = True
                trailing_code = trailing_code or semicolons > 0
                closing = sql.find(tag, end + 1)
                if closing != -1:
                    position = closing + len(tag)
                    continue
            position += 1
            continue
        if sql.startswith("--", position):
            newline = sql.find("\n", position)
            position = length if newline == -1 else newline + 1
            continue
        if sql.startswith("/*", position):
            closing = sql.find("*/", position + 2)
            position = length if closing == -1 else closing + 2
            continue
        if char == ";":
            saw_code = True
            semicolons += 1
            position += 1
            continue
        if not char.isspace():
            saw_code = True
            if semicolons > 0:
                trailing_code = True
        position += 1
    if not saw_code:
        return False
    if semicolons > 1:
        return False
    if semicolons == 1 and trailing_code:
        return False
    return True


def _convert_value(value):
    """Serialize one result cell per the frozen minimal conversion set.

    NULL/bool/int/float stay native JSON; Decimal (numeric columns) becomes a
    decimal string; date/time/datetime/timedelta (timestamps, intervals) and
    UUID become stable ISO/canonical strings; anything else falls back to
    ``str()`` so the output is always exactly one JSON object.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.datetime):  # covers timestamptz (tz-aware) values
        return value.isoformat()
    if isinstance(value, (dt.date, dt.time, dt.timedelta)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _fail("input_error", "stdin is not valid JSON")
    if not isinstance(payload, dict):
        return _fail("input_error", "request must be a JSON object")
    unknown = set(payload) - {"sql"}
    if unknown:
        return _fail("input_error", f"unknown fields: {sorted(unknown)}")
    sql = payload.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        return _fail("input_error", "'sql' must be a non-empty string")
    if not _statement_is_single(sql):
        return _fail("input_error", "exactly one SQL statement is required")

    dsn = os.environ.get(DSN_ENV)
    if not dsn:
        return _fail("config_error", f"{DSN_ENV} is not set")

    try:
        import psycopg
        from psycopg.conninfo import make_conninfo

        try:
            conninfo = make_conninfo(dsn, options=READ_ONLY_OPTIONS)
        except Exception as exc:  # unparsable DSN
            return _fail("config_error", f"invalid DSN: {exc}")

        try:
            with psycopg.connect(conninfo) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                    columns = [desc.name for desc in cursor.description or []]
                    rows = [
                        [_convert_value(value) for value in row] for row in cursor.fetchall()
                    ]
        except psycopg.Error as exc:
            return _fail("database_error", str(exc).strip() or exc.__class__.__name__)
    except ImportError as exc:  # psycopg unavailable in this interpreter
        return _fail("config_error", f"adapter dependency missing: {exc}")

    json.dump(
        {"ok": True, "columns": columns, "rows": rows},
        sys.stdout,
        ensure_ascii=False,
        default=_convert_value,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
