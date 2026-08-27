"""R3.0-005 A1/A2: SQL execution adapter contract tests.

Drives ``scripts/r3-0-005/sql_exec_adapter.py`` as a subprocess exactly the way
the Consumer Agent chain does (stdin JSON -> stdout JSON). Tests that need the
scenario database are skipped unless ``R3005_SQL_ADAPTER_DSN`` is set (gating
precedent: ``RUN_OXIGRAPH_SPARQL_RUNNER_TESTS``); contract tests that need no
database always run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ADAPTER = (
    Path(__file__).resolve().parents[2] / "scripts" / "r3-0-005" / "sql_exec_adapter.py"
)
DSN = os.environ.get("R3005_SQL_ADAPTER_DSN")
SCHEMA = "industrial_service_v3"

requires_dsn = pytest.mark.skipif(
    not DSN, reason="R3005_SQL_ADAPTER_DSN is not set (scenario PostgreSQL unavailable)"
)


def run_adapter(stdin_text: str, *, dsn: str | None = DSN) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if dsn is None:
        env.pop("R3005_SQL_ADAPTER_DSN", None)
    else:
        env["R3005_SQL_ADAPTER_DSN"] = dsn
    return subprocess.run(
        [sys.executable, str(ADAPTER)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _direct_scalar(sql: str):
    """Independent baseline path: direct psycopg, no adapter involved."""
    import psycopg

    with psycopg.connect(DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            row = cursor.fetchone()
            return row[0] if row else None


# ---------------------------------------------------------------- A1: contract


def test_missing_dsn_is_config_error():
    proc = run_adapter(json.dumps({"sql": "SELECT 1"}), dsn=None)
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "config_error"
    assert "Traceback" not in proc.stderr


def test_bad_dsn_is_rejected_without_stacktrace():
    proc = run_adapter(
        json.dumps({"sql": "SELECT 1"}), dsn="not a valid dsn :://"
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["error"]["kind"] in {"config_error", "database_error"}


@pytest.mark.parametrize(
    "stdin_text",
    [
        "",
        "not json",
        "[]",
        json.dumps({"sql": "SELECT 1", "extra": 1}),
        json.dumps({"sql": 42}),
        json.dumps({"sql": "   "}),
    ],
)
def test_invalid_payloads_are_input_errors(stdin_text):
    proc = run_adapter(stdin_text)
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "input_error"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; SELECT 2",
        "SELECT 1; SELECT 2;",
        " SELECT 1 ; -- trailing statement\n SELECT 2",
    ],
)
def test_multi_statement_payloads_are_input_errors(sql):
    proc = run_adapter(json.dumps({"sql": sql}))
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "input_error"


@requires_dsn
def test_semicolons_inside_strings_and_comments_are_not_statement_separators():
    sql = (
        "SELECT count(*) FROM industrial_service_v3.work_orders "
        "WHERE status = 'RESOLVED;NOT-A-STATEMENT' -- ; comment\n"
    )
    proc = run_adapter(json.dumps({"sql": sql}))
    assert proc.returncode == 0, proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True


# ------------------------------------------------- S1/S2: success path with DB


@requires_dsn
def test_select_returns_columns_rows_and_exit_zero():
    sql = (
        f"SELECT count(*) FROM {SCHEMA}.work_orders WHERE status = 'RESOLVED'"
    )
    proc = run_adapter(json.dumps({"sql": sql}))
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["columns"] == ["count"]
    expected = _direct_scalar(sql)
    assert payload["rows"] == [[expected]]


@requires_dsn
def test_stdout_is_exactly_one_json_object_on_both_paths():
    ok = run_adapter(json.dumps({"sql": f"SELECT 1 AS one FROM {SCHEMA}.work_orders LIMIT 1"}))
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["ok"] is True
    assert ok.stdout.count("\n") == 1

    failing = run_adapter(json.dumps({"sql": f"SELECT * FROM {SCHEMA}.missing_table"}))
    assert failing.returncode == 1
    assert json.loads(failing.stdout)["ok"] is False
    assert failing.stdout.count("\n") == 1


# ------------------------------------------------------------- B3/F1: failures


@requires_dsn
def test_database_error_passthrough_has_no_stacktrace():
    proc = run_adapter(json.dumps({"sql": f"SELECT * FROM {SCHEMA}.no_such_table_xyz"}))
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "database_error"
    assert "no_such_table_xyz" in payload["error"]["message"]
    assert "Traceback" not in proc.stderr
    assert "Traceback" not in proc.stdout


def test_unreachable_dsn_is_database_error():
    proc = run_adapter(
        json.dumps({"sql": "SELECT 1"}),
        dsn="postgresql://127.0.0.1:1/none?connect_timeout=1",
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "database_error"


# ----------------------------------------------------------- A2/B1: read-only


@requires_dsn
def test_write_statements_are_rejected_and_data_is_unchanged():
    before = _direct_scalar(f"SELECT count(*) FROM {SCHEMA}.work_orders")

    statements = [
        (
            f"INSERT INTO {SCHEMA}.work_orders (work_order_id, work_order_number, "
            "incident_id, opened_at, status, created_by) "
            "VALUES ('probe-1', 'probe-1', 'probe-1', now(), 'OPEN', 'probe')"
        ),
        f"UPDATE {SCHEMA}.work_orders SET status = 'OPEN'",
        f"DELETE FROM {SCHEMA}.work_orders",
        f"CREATE TABLE {SCHEMA}.r3005_adapter_probe (id text)",
        (
            f"WITH moved AS (DELETE FROM {SCHEMA}.work_orders RETURNING work_order_id) "
            "SELECT count(*) FROM moved"
        ),
    ]
    for sql in statements:
        proc = run_adapter(json.dumps({"sql": sql}))
        assert proc.returncode == 1, sql
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False
        assert payload["error"]["kind"] == "database_error"
        assert "read-only" in payload["error"]["message"], payload

    after = _direct_scalar(f"SELECT count(*) FROM {SCHEMA}.work_orders")
    assert after == before
    probe_exists = _direct_scalar(
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = '{SCHEMA}' AND table_name = 'r3005_adapter_probe'"
    )
    assert probe_exists == 0

    # plain SELECT is unaffected by the read-only connection setting
    ok = run_adapter(json.dumps({"sql": f"SELECT count(*) FROM {SCHEMA}.work_orders"}))
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["rows"] == [[before]]


# ------------------------------------------ S3b: result JSON type contract
# Frozen minimal conversion set (design §3.2): NULL/bool/int/float native;
# numeric -> decimal string; date/time/timestamp/interval/UUID -> stable
# ISO/canonical string; anything else -> str().


_DECIMAL_STRING = re.compile(r"^-?\d+(\.\d+)?$")


@requires_dsn
def test_numeric_aggregate_serializes_as_decimal_string():
    sql = f"SELECT AVG(standard_cost) FROM {SCHEMA}.spare_parts"
    proc = run_adapter(json.dumps({"sql": sql}))
    assert proc.returncode == 0, proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    value = payload["rows"][0][0]
    assert isinstance(value, str)
    assert _DECIMAL_STRING.match(value), value
    assert value == str(_direct_scalar(sql))


@requires_dsn
def test_timestamp_and_date_columns_serialize_as_iso_strings():
    sql = (
        f"SELECT opened_at, opened_at::date FROM {SCHEMA}.work_orders "
        f"ORDER BY work_order_id LIMIT 1"
    )
    proc = run_adapter(json.dumps({"sql": sql}))
    assert proc.returncode == 0, proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    timestamp_cell, date_cell = payload["rows"][0]
    assert isinstance(timestamp_cell, str) and isinstance(date_cell, str)
    assert "T" in timestamp_cell  # ISO 8601 timestamp, not str(datetime) spacing
    assert _direct_baseline_row(sql) == [timestamp_cell, date_cell]


def _direct_baseline_row(sql: str) -> list[str]:
    import psycopg

    with psycopg.connect(DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            row = cursor.fetchone()
    assert row is not None
    return [value.isoformat() for value in row]


@requires_dsn
def test_null_bool_int_float_stay_native_json():
    sql = "SELECT NULL::text AS n, TRUE AS t, 1 AS i, 1.5::float8 AS f, 1.5::numeric AS dec"
    proc = run_adapter(json.dumps({"sql": sql}))
    assert proc.returncode == 0, proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["rows"][0] == [None, True, 1, 1.5, "1.5"]
    raw = proc.stdout
    assert "NaN" not in raw and "Infinity" not in raw
