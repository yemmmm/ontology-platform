#!/usr/bin/env python3
"""R3.0-006 externalized Consumer rounds driver (design §3.G6, test plan T-G6).

Platform-external acceptance tooling for the R3.0-006 end-to-end SQL rounds. It
reuses the ``scripts/r3-0-005`` run shape (spawn the platform MCP server per
round principal → expose only the three authorized semantic read tools plus a
local ``execute_sql`` tool that shells out to the frozen
``scripts/r3-0-005/sql_exec_adapter.py`` → OpenAI-compatible tool loop → full
redacted transcript → driver-side verdict) with one difference: the questions
and the expected SQL results are **external** to this file.

Rounds file contract (``--rounds <path>``, JSON)::

    {
      "rounds": [
        {
          "question_id": "CQ-01",
          "principal_env": "R3006_SMOKE_KEY_GRANT",
          "principal_name": "grant",
          "question": "<natural-language business question>",
          "expected_rows": [["<value>", ...], ...],
          "expected_columns": ["col_a", "col_b"],
          "expected_rows_order_matters": false,
          "expected_answer_points": ["<answer wording hint>"],
          "protected": {
            "forbidden_in_sql": ["<identifier>"],
            "forbidden_in_answer": ["<phrase>"],
            "require_no_sql": true,
            "require_unconfirmable": true
          }
        }
      ]
    }

Only ``question_id``, ``principal_env`` and ``question`` are required.
``expected_rows`` rows are positional lists written in the adapter's frozen
005 serialization (see below). Unknown fields are rejected (fail-closed).

Isolation (test plan T-G6-2): everything except the natural-language question
and the runtime ``discover_semantic_scopes`` context stays on the driver side.
Expected answers, ``expected_rows`` and protected assertions never enter any
prompt string, and this file hardcodes no scenario, customer or fixture name.

Row-level verdict (test plan T-G6-3): SQL correctness is decided **only** by
comparing the actual ``execute_sql`` adapter rows against ``expected_rows``.
The judged result is the **final** ``execute_sql`` attempt (the last statement
actually executed), never an earlier success: every attempt is kept as
evidence, and a final attempt that ends in an adapter error is reported as an
incomplete round instead of falling back to a previous result. A round with
``expected_rows`` but no successful adapter execution can never PASS.
Cell normalization follows the frozen 005 conversion set and is class-strict:

- ``null`` / ``bool`` / ``number`` / ``text`` are distinct classes; a class
  difference is a difference (``5`` ≠ ``"5"``, ``true`` ≠ ``1``, ``null`` ≠
  ``"NULL"``, ``"001"`` ≠ ``"1"``).
- JSON numbers compare numerically (``3`` == ``3.0``).
- JSON strings compare **exactly**: the adapter's output cannot distinguish a
  SQL decimal serialized as text from a VARCHAR business identifier, so no
  numeric equivalence is applied to strings. ``expected_rows`` authors must
  use the exact frozen adapter serialization for decimal columns.
- Rows compare as a multiset by default (row order is not significant for SQL
  without ``ORDER BY``); ``expected_rows_order_matters: true`` compares
  positionally instead.

Natural-language answer checks are recorded as **evidence only** and are
excluded from every verdict: they can never establish or restore a PASS.
Protected assertions (forbidden substrings, ``require_no_sql``,
``require_unconfirmable``) are reported as the separate protection conclusion;
they can only turn a round into a FAIL, never into a PASS.

A full round PASS additionally requires the interaction to have **completed**
(the model produced a final answer inside ``max_turns`` **and** the initial
``discover_semantic_scopes`` context read succeeded): an exhausted interaction
or a failed semantic discovery is recorded as runtime-incomplete at that first
blocking layer and cannot PASS, even when the model answers 无法确认 — an MCP
outage is not evidence of correct authorization behavior. SQL-row evidence
stays separately visible.

A round that declares neither ``expected_rows`` nor ``protected`` assertions
has no oracle; ``load_rounds`` rejects it and ``judge_round`` reports it as
not evaluated rather than PASS.

The ``client_factory`` / ``mcp_session_factory`` / ``execute_sql_fn`` keyword
parameters of ``run_round`` are controlled fixtures for the mechanical tests
only; the driver CLI always uses the real HTTP client, real MCP session and
the frozen adapter subprocess.

Environment (005 naming; the adapter reads only its own variable):

- ``R3006_SMOKE_KEY_*``        per-principal platform API keys, referenced by
  each round's ``principal_env`` (defaults checked: ``R3006_SMOKE_KEY_GRANT``,
  ``R3006_SMOKE_KEY_NOGRANT``)
- ``R3005_SQL_ADAPTER_DSN``    adapter database DSN (business rows stay in
  PostgreSQL; nothing is copied anywhere)
- ``R3006_SMOKE_LLM_BASE_URL`` / ``_API_KEY`` / ``_MODEL``
- ``R3006_SMOKE_BACKEND_URL``  (default ``http://127.0.0.1:8001``)
- ``R3006_SMOKE_MAX_TURNS``    (default 24)

``--check`` truthfully reports each item (rounds file, credentials, adapter DSN
and adapter contract, backend health, MCP tool surface, LLM endpoint), exits
non-zero when something is missing, and never claims that any real SQL
acceptance passed: it executes no Consumer round at all.

Boundaries (design §3.G6.4): this driver is the tool for the later authorized
SQL rounds and is **not** a prerequisite for starting semantic modeling. It is
no generic adapter framework: no data authorization, no policy rewriting, no
auditing, no connector framework. Adapter results are passed through verbatim;
this file never fabricates SQL success. Fixture subprocess output must never be
reported as a real semantic or SQL acceptance PASS.

Interpreter: run with the backend venv (``mcp``/``httpx`` live there), e.g.
``uv run --project backend python scripts/r3-0-006/consumer_rounds.py --check``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = REPO_ROOT / "scripts" / "r3-0-005" / "sql_exec_adapter.py"
DEFAULT_EVIDENCE_DIR = (
    REPO_ROOT
    / "docs/delivery/evidence/2026-09-09-v3-execution-gap-closure/consumer-rounds"
)

ALLOWED_MCP_TOOLS = (
    "discover_semantic_scopes",
    "query_semantic_context",
    "get_semantic_read_model",
)
SQL_TOOL = "execute_sql"

DSN_ENV = "R3005_SQL_ADAPTER_DSN"  # the frozen adapter reads only this variable
BACKEND_URL_ENV = "R3006_SMOKE_BACKEND_URL"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8001"
DEFAULT_PRINCIPAL_ENVS = ("R3006_SMOKE_KEY_GRANT", "R3006_SMOKE_KEY_NOGRANT")
LLM_BASE_ENV = "R3006_SMOKE_LLM_BASE_URL"
LLM_KEY_ENV = "R3006_SMOKE_LLM_API_KEY"
LLM_MODEL_ENV = "R3006_SMOKE_LLM_MODEL"
MAX_TURNS_ENV = "R3006_SMOKE_MAX_TURNS"

ADAPTER_TIMEOUT_SECONDS = 120
LLM_TIMEOUT_SECONDS = 180
DEFAULT_MAX_TURNS = 24
MAX_TOOL_RESULT_CHARS = 16000
MAX_DISCOVERY_CHARS = 6000

UNCONFIRMABLE_RE = re.compile(r"无法确认|不能确认|无法核实")

# Generic Consumer prompt: role, tool discipline and the unconfirmable terminal
# shape only. No scenario, customer, fixture, table or metric name may appear
# here; the authorized context comes from the runtime discovery result.
SYSTEM_PROMPT = """\
你是业务数据问数 Consumer Agent，负责基于当前主体已授权的语义上下文回答自然语言问题。

规则（必须严格遵守）：
1. 第一步必须以"空 query"调用 discover_semantic_scopes（即不传 query）枚举当前
   主体已授权的项目/本体 scope。注意：该工具的 query 参数只对项目名称/本体名称
   做词法匹配，不能用业务词汇检索；应先空 query 枚举，再从返回项中按名称定位
   目标本体；queryable 为 true 的本体条目含 graph_set_id 字段，直接作为
   get_semantic_read_model 所需的 graph_set_id 使用，禁止猜测。
2. 之后用 query_semantic_context（resource_types 包含 mapping/metric）检索与问题
   相关的概念与指标；再用 get_semantic_read_model 读取 detail 模板，取得表、列、
   join、枚举含义与指标口径。
3. 只允许使用上述工具返回中出现的表名、列名、join 步骤、枚举值与指标口径生成
   SQL；禁止猜测，禁止查询 information_schema/pg_catalog 等原始 Schema，禁止
   使用授权上下文之外的任何标识符。
4. SQL 通过 execute_sql 工具执行，每次单条 SELECT 语句。
5. 回答时说明所用业务口径（指标名、聚合、粒度、时间字段、过滤、空值/分母规则）
   与关键映射依据。
6. 如果已授权的语义不足以安全生成 SQL，直接回答"无法确认"，不要说明原因是未
   建模、不存在还是无权限，不要给出任何数值或猜测。
"""


class DriverError(RuntimeError):
    """Blocked before any round could run (configuration or contract problem)."""


class RoundsFileError(DriverError):
    """The external rounds file does not satisfy the documented contract."""


# ---------------------------------------------------------------------------
# External rounds file
# ---------------------------------------------------------------------------

ROUND_FIELDS = {
    "question_id",
    "principal_env",
    "principal_name",
    "question",
    "expected_rows",
    "expected_columns",
    "expected_rows_order_matters",
    "expected_answer_points",
    "protected",
}
REQUIRED_ROUND_FIELDS = {"question_id", "principal_env", "question"}
TOP_LEVEL_FIELDS = {"rounds", "description"}
PROTECTED_FIELDS = {
    "forbidden_in_sql",
    "forbidden_in_answer",
    "require_no_sql",
    "require_unconfirmable",
}
PRINCIPAL_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def load_rounds(path: Path) -> list[dict[str, Any]]:
    """Load and validate the external rounds file (fail-closed, no defaults)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RoundsFileError(f"cannot read rounds file {path}: {exc}") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RoundsFileError(f"rounds file {path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise RoundsFileError("rounds file must contain one JSON object")
    unknown = set(document) - TOP_LEVEL_FIELDS
    if unknown:
        raise RoundsFileError(f"unknown top-level fields: {sorted(unknown)}")
    entries = document.get("rounds")
    if not isinstance(entries, list) or not entries:
        raise RoundsFileError("'rounds' must be a non-empty list")

    rounds: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"rounds[{index}]"
        if not isinstance(entry, dict):
            raise RoundsFileError(f"{where} must be a JSON object")
        unknown = set(entry) - ROUND_FIELDS
        if unknown:
            raise RoundsFileError(f"{where} has unknown fields: {sorted(unknown)}")
        missing = REQUIRED_ROUND_FIELDS - set(entry)
        if missing:
            raise RoundsFileError(f"{where} is missing fields: {sorted(missing)}")
        question_id = entry["question_id"]
        if not isinstance(question_id, str) or not question_id.strip():
            raise RoundsFileError(f"{where}.question_id must be a non-empty string")
        if question_id in seen:
            raise RoundsFileError(f"{where}.question_id duplicates {question_id!r}")
        seen.add(question_id)
        principal_env = entry["principal_env"]
        if not isinstance(principal_env, str) or not PRINCIPAL_ENV_RE.match(principal_env):
            raise RoundsFileError(
                f"{where}.principal_env must be an environment variable name"
            )
        if not isinstance(entry["question"], str) or not entry["question"].strip():
            raise RoundsFileError(f"{where}.question must be a non-empty string")
        normalized = {
            "question_id": question_id,
            "principal_env": principal_env,
            "principal_name": entry.get("principal_name") or principal_env,
            "question": entry["question"],
            "expected_rows": _validate_rows(entry, where),
            "expected_columns": _validate_columns(entry, where),
            "expected_rows_order_matters": entry.get("expected_rows_order_matters", False),
            "expected_answer_points": _validate_string_list(
                entry.get("expected_answer_points"), f"{where}.expected_answer_points"
            ),
            "protected": _validate_protected(entry.get("protected"), where),
        }
        if not isinstance(normalized["expected_rows_order_matters"], bool):
            raise RoundsFileError(
                f"{where}.expected_rows_order_matters must be a boolean"
            )
        if normalized["expected_rows"] is None and not normalized["protected"]:
            raise RoundsFileError(
                f"{where} has no oracle: declare expected_rows and/or protected "
                "assertions, otherwise the round cannot be evaluated"
            )
        rounds.append(normalized)
    return rounds


def _validate_rows(entry: dict[str, Any], where: str) -> list[list[Any]] | None:
    if "expected_rows" not in entry or entry["expected_rows"] is None:
        return None
    rows = entry["expected_rows"]
    if not isinstance(rows, list):
        raise RoundsFileError(f"{where}.expected_rows must be a list of row lists")
    for index, row in enumerate(rows):
        if not isinstance(row, list):
            raise RoundsFileError(
                f"{where}.expected_rows[{index}] must be a list of cell values"
            )
    return rows


def _validate_columns(entry: dict[str, Any], where: str) -> list[str] | None:
    if "expected_columns" not in entry or entry["expected_columns"] is None:
        return None
    columns = _validate_string_list(entry["expected_columns"], f"{where}.expected_columns")
    if columns is None:
        raise RoundsFileError(f"{where}.expected_columns must be a list of names")
    if len(set(columns)) != len(columns):
        raise RoundsFileError(f"{where}.expected_columns must be unique")
    return columns


def _validate_string_list(value: Any, label: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise RoundsFileError(f"{label} must be a list of non-empty strings")
    return value


def _validate_protected(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RoundsFileError(f"{where}.protected must be a JSON object")
    unknown = set(value) - PROTECTED_FIELDS
    if unknown:
        raise RoundsFileError(f"{where}.protected has unknown fields: {sorted(unknown)}")
    protected: dict[str, Any] = {}
    for key in ("forbidden_in_sql", "forbidden_in_answer"):
        if key in value:
            protected[key] = _validate_string_list(value[key], f"{where}.protected.{key}") or []
    for key in ("require_no_sql", "require_unconfirmable"):
        if key in value:
            if not isinstance(value[key], bool):
                raise RoundsFileError(f"{where}.protected.{key} must be a boolean")
            protected[key] = value[key]
    return protected


# ---------------------------------------------------------------------------
# Row normalization and comparison (driver-side truth; nothing here reads or
# writes prompts)
# ---------------------------------------------------------------------------


def canonical_decimal(value: Decimal) -> str:
    """Plain, locale-free decimal form with trailing zeros removed."""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def normalize_cell(value: Any) -> tuple[str, str]:
    """Classify one cell per the frozen 005 serialization set.

    Returns ``(class, canonical)``. JSON strings are preserved exactly: the
    adapter output cannot tell a serialized decimal from a VARCHAR identifier,
    so no numeric equivalence is applied to text. Only actual JSON numeric
    types get numeric comparison (bool stays distinct from number).
    """
    if value is None:
        return ("null", "null")
    if isinstance(value, bool):  # before int: bool is an int subclass
        return ("bool", "true" if value else "false")
    if isinstance(value, (int, float)):
        return ("number", canonical_decimal(Decimal(str(value))))
    if isinstance(value, str):
        return ("text", value)
    return ("text", str(value))


def normalize_row(row: list[Any]) -> tuple[tuple[str, str], ...]:
    return tuple(normalize_cell(value) for value in row)


def _format_cell(cell: tuple[str, str]) -> str:
    return cell[1] if cell[0] in ("null", "bool", "number") else f"{cell[0]}:{cell[1]!r}"


def _format_row(row: tuple[tuple[str, str], ...]) -> list[str]:
    return [_format_cell(cell) for cell in row]


def judge_sql_rows(
    round_def: dict[str, Any], executed_sql: list[dict[str, Any]]
) -> dict[str, Any]:
    """Judge SQL correctness from the final ``execute_sql`` attempt only.

    Earlier attempts stay in the evidence but are never used as a fallback: an
    expected result produced by a superseded statement does not pass, and a
    corrected final statement is the one that is compared.
    """
    expected_rows = round_def["expected_rows"]
    if expected_rows is None:
        return {
            "verdict": "not_applicable",
            "reason": "round declares no expected_rows (no SQL result to judge)",
            "order_matters": round_def["expected_rows_order_matters"],
            "judged_attempt_index": None,
            "attempts_recorded": len(executed_sql),
        }
    if not executed_sql:
        return {
            "verdict": "not_executed",
            "reason": (
                "no execute_sql call was made; expected_rows exist but nothing ran"
            ),
            "order_matters": round_def["expected_rows_order_matters"],
            "judged_attempt_index": None,
            "attempts_recorded": 0,
        }
    final_index = len(executed_sql) - 1
    final = executed_sql[final_index]
    payload = final["adapter_output"]
    if not payload.get("ok"):
        error = payload.get("error") or {}
        return {
            "verdict": "adapter_error",
            "reason": (
                "final execute_sql attempt returned an adapter error "
                f"({error.get('kind')}): {error.get('message', '')}"
            ),
            "order_matters": round_def["expected_rows_order_matters"],
            "judged_attempt_index": final_index,
            "attempts_recorded": len(executed_sql),
            "final_sql": final["sql"],
            "adapter_error": error,
        }
    comparison = compare_rows(
        expected_rows=expected_rows,
        expected_columns=round_def.get("expected_columns"),
        actual_columns=payload.get("columns", []),
        actual_rows=payload.get("rows", []),
        order_matters=round_def.get("expected_rows_order_matters", False),
    )
    comparison.update(
        {
            "judged_attempt_index": final_index,
            "attempts_recorded": len(executed_sql),
            "final_sql": final["sql"],
        }
    )
    return comparison


def compare_rows(
    *,
    expected_rows: list[list[Any]] | None,
    expected_columns: list[str] | None,
    actual_columns: list[str],
    actual_rows: list[list[Any]],
    order_matters: bool,
) -> dict[str, Any]:
    """Compare actual adapter rows with ``expected_rows`` (the only PASS source)."""
    if expected_rows is None:
        return {
            "verdict": "not_applicable",
            "reason": "round declares no expected_rows (no SQL result to judge)",
            "order_matters": order_matters,
        }

    checks: list[dict[str, Any]] = []
    column_check: dict[str, Any] = {
        "performed": expected_columns is not None,
        "expected": expected_columns,
        "actual": actual_columns,
        "pass": True,
        "detail": "not performed (no expected_columns declared)",
    }
    if expected_columns is not None:
        if expected_columns != actual_columns:
            column_check["pass"] = False
            column_check["detail"] = (
                "column mismatch: "
                f"expected {expected_columns} (ordered), actual {actual_columns}"
            )
        else:
            column_check["detail"] = f"columns match: {actual_columns}"
    checks.append(("columns", column_check))

    expected_normalized = [normalize_row(row) for row in expected_rows]
    actual_normalized = [normalize_row(row) for row in actual_rows]

    count_check = {
        "expected": len(expected_normalized),
        "actual": len(actual_normalized),
        "pass": len(expected_normalized) == len(actual_normalized),
    }
    checks.append(("row_count", count_check))

    row_compare: dict[str, Any] = {
        "mode": "sequence" if order_matters else "multiset",
        "pass": False,
        "missing_expected": [],
        "unexpected_actual": [],
        "first_difference": None,
    }
    if order_matters:
        for index, (expected, actual) in enumerate(
            zip(expected_normalized, actual_normalized)
        ):
            if expected != actual:
                row_compare["first_difference"] = {
                    "row_index": index,
                    "expected": _format_row(expected),
                    "actual": _format_row(actual),
                }
                break
        row_compare["pass"] = count_check["pass"] and row_compare["first_difference"] is None
    else:
        expected_counts = Counter(expected_normalized)
        actual_counts = Counter(actual_normalized)
        missing = expected_counts - actual_counts
        unexpected = actual_counts - expected_counts
        row_compare["missing_expected"] = [_format_row(row) for row in missing.elements()]
        row_compare["unexpected_actual"] = [
            _format_row(row) for row in unexpected.elements()
        ]
        row_compare["pass"] = not missing and not unexpected

    # sequence mode: equal row counts and no positional difference (above);
    # multiset mode: no missing expected row and no unexpected actual row.
    checks.append(("rows", row_compare))

    verdict_pass = column_check["pass"] and count_check["pass"] and row_compare["pass"]
    details: list[str] = [str(column_check["detail"])]
    if not count_check["pass"]:
        details.append(
            f"row count differs: expected {count_check['expected']}, "
            f"actual {count_check['actual']}"
        )
    if not row_compare["pass"]:
        if row_compare["first_difference"]:
            difference = row_compare["first_difference"]
            details.append(
                f"first row difference at index {difference['row_index']}: "
                f"expected {difference['expected']}, actual {difference['actual']}"
            )
        if row_compare["missing_expected"]:
            details.append(f"missing expected rows: {row_compare['missing_expected']}")
        if row_compare["unexpected_actual"]:
            details.append(f"unexpected actual rows: {row_compare['unexpected_actual']}")
    return {
        "verdict": "pass" if verdict_pass else "fail",
        "order_matters": order_matters,
        "column_check": column_check,
        "row_count": count_check,
        "row_compare": row_compare,
        "expected_rows": [_format_row(row) for row in expected_normalized],
        "actual_rows": [_format_row(row) for row in actual_normalized],
        "detail": "; ".join(details),
    }


# ---------------------------------------------------------------------------
# Protection and evidence-only checks (FAIL direction only; never a PASS source)
# ---------------------------------------------------------------------------


def check_protection(round_def: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    protected = round_def.get("protected") or {}
    checks: list[dict[str, Any]] = []
    sql_texts = [entry["sql"] for entry in record["executed_sql"]]
    sql_blob = "\n".join(sql_texts)
    answer = record.get("answer", "")

    for term in protected.get("forbidden_in_sql", []):
        hit = term.lower() in sql_blob.lower()
        checks.append(
            {
                "name": "forbidden_in_sql",
                "term": term,
                "pass": not hit,
                "detail": "found in executed SQL" if hit else "",
            }
        )
    for term in protected.get("forbidden_in_answer", []):
        hit = term.lower() in answer.lower()
        checks.append(
            {
                "name": "forbidden_in_answer",
                "term": term,
                "pass": not hit,
                "detail": "found in final answer" if hit else "",
            }
        )
    if protected.get("require_no_sql"):
        checks.append(
            {
                "name": "require_no_sql",
                "term": "",
                "pass": not sql_texts,
                "detail": f"{len(sql_texts)} SQL statement(s) executed" if sql_texts else "",
            }
        )
    if protected.get("require_unconfirmable"):
        matched = bool(UNCONFIRMABLE_RE.search(answer))
        checks.append(
            {
                "name": "require_unconfirmable",
                "term": "",
                "pass": matched,
                "detail": "" if matched else "answer lacks an unconfirmable terminal shape",
            }
        )
    failed = [entry for entry in checks if not entry["pass"]]
    return {
        "verdict": "fail" if failed else "pass",
        "role": "protection conclusions only; can only produce FAIL",
        "checks": checks,
    }


def collect_answer_evidence(
    round_def: dict[str, Any], record: dict[str, Any]
) -> dict[str, Any]:
    """Display-only answer wording evidence. Excluded from every verdict."""
    answer = record.get("answer", "")
    points = [
        {"point": point, "present": point.lower() in answer.lower()}
        for point in round_def["expected_answer_points"]
    ]
    return {
        "role": "evidence_only",
        "verdict_role": (
            "never decides PASS/FAIL; SQL correctness comes from row comparison"
        ),
        "points": points,
    }


def judge_round(round_def: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Round verdict: oracle + completed interaction + row comparison + protection.

    Answer wording never decides anything. An incomplete interaction (max turns
    exhausted, aborted round, or failed initial semantic discovery) cannot
    produce a full PASS even though its SQL-row evidence stays separately
    visible, and a round with no oracle at all is reported as not evaluated.
    """
    sql_rows = record["row_comparison"]
    protection = record["protection"]
    completion = record.get("runtime_completion", {"completed": False, "reason": "unknown"})
    row_pass = sql_rows["verdict"] in ("pass", "not_applicable")
    has_oracle = round_def.get("expected_rows") is not None or bool(round_def.get("protected"))
    evaluation = "full" if has_oracle else "not_evaluated_no_oracle"
    return {
        "question_id": round_def["question_id"],
        "evaluation": evaluation,
        "passed": bool(
            has_oracle
            and completion["completed"]
            and row_pass
            and protection["verdict"] == "pass"
        ),
        "runtime_completion": completion["reason"],
        "sql_rows_verdict": sql_rows["verdict"],
        "protection_verdict": protection["verdict"],
        "answer_evidence_role": "evidence_only (excluded from verdicts)",
    }


# ---------------------------------------------------------------------------
# execute_sql tool: the frozen external adapter, results passed through verbatim
# ---------------------------------------------------------------------------


def _adapter_python() -> str:
    venv_python = REPO_ROOT / "backend/.venv/bin/python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def run_execute_sql(
    sql: str,
    *,
    adapter: Path = ADAPTER,
    timeout: int = ADAPTER_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute one SQL statement through the frozen 005 adapter subprocess.

    The adapter's JSON contract is returned verbatim (``ok`` / ``columns`` /
    ``rows`` or ``error.kind`` in ``config_error`` / ``input_error`` /
    ``database_error``). Only failures of the adapter process itself — crash,
    non-JSON stdout, timeout — are reported as ``driver_error``; the adapter's
    own error kinds and messages are never rewritten or downplayed here.
    """
    environment = dict(env if env is not None else os.environ)
    try:
        proc = subprocess.run(
            [sys.executable, str(adapter)],
            input=json.dumps({"sql": sql}),
            capture_output=True,
            text=True,
            env=environment,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": {
                "kind": "driver_error",
                "message": f"adapter did not finish within {timeout}s",
            },
        }
    except OSError as exc:
        return {"ok": False, "error": {"kind": "driver_error", "message": str(exc)}}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": {
                "kind": "driver_error",
                "message": (
                    f"adapter stdout is not JSON (exit {proc.returncode}): "
                    f"{proc.stdout[:400]!r} stderr: {proc.stderr[:400]!r}"
                ),
            },
        }
    payload["adapter_exit_code"] = proc.returncode
    return payload


# ---------------------------------------------------------------------------
# MCP session with the narrowed tool surface (005 run shape)
# ---------------------------------------------------------------------------


class McpSession:
    """Stdio MCP client exposing only the three authorized semantic read tools."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = None
        self._stdio = None
        self._client = None

    async def __aenter__(self) -> "McpSession":
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=_uv_executable(),
            args=[
                "run",
                "--directory",
                str(REPO_ROOT / "backend"),
                "python",
                "-m",
                "app.mcp.server",
            ],
            env={**os.environ, "ONTOLOGY_MCP_API_KEY": self.api_key},
        )
        self._stdio = stdio_client(params)
        read, write = await self._stdio.__aenter__()
        self._session = ClientSession(read, write)
        self._client = await self._session.__aenter__()
        await self._client.initialize()
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._session is not None:
            await self._session.__aexit__(*exc_info)
        if self._stdio is not None:
            await self._stdio.__aexit__(*exc_info)

    async def narrowed_tool_names(self) -> list[str]:
        listing = await self._client.list_tools()
        return [tool.name for tool in listing.tools if tool.name in ALLOWED_MCP_TOOLS]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        result = await self._client.call_tool(name, arguments)
        parts = [
            block.text
            for block in result.content
            if getattr(block, "text", None) is not None
        ]
        return "\n".join(parts)


def _uv_executable() -> str:
    for candidate in (REPO_ROOT / "backend/.venv/bin/uv", Path.home() / ".local/bin/uv"):
        if candidate.exists():
            return str(candidate)
    return "uv"


# ---------------------------------------------------------------------------
# Prompt assembly: question + runtime authorized context. Nothing else.
# ---------------------------------------------------------------------------


def build_user_prompt(question: str, runtime_context: str) -> str:
    return (
        "当前主体已授权的语义范围（运行时 discover_semantic_scopes 动态取得，非预设）：\n"
        f"{runtime_context}\n\n"
        "业务问题：\n"
        f"{question}\n"
    )


def build_messages(question: str, runtime_context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, runtime_context)},
    ]


def _llm_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "discover_semantic_scopes",
                "description": "枚举当前主体已授权的项目/本体查询范围与就绪状态。"
                "query 参数只对项目名称/本体名称做词法匹配，不能用业务词检索；"
                "应先不传 query 枚举全部可用 scope，再从返回项中按名称定位目标本体。"
                "queryable 为 true 的本体条目含 graph_set_id 字段，可直接作为 "
                "get_semantic_read_model 的 graph_set_id 使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "queryable": {"type": "boolean"},
                        "limit": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_semantic_context",
                "description": "按自然语言检索已授权的语义上下文（含 mapping/metric 候选）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string"},
                        "scope_mode": {"type": "string", "enum": ["project", "ontologies"]},
                        "query": {"type": "string"},
                        "resource_types": {"type": "array", "items": {"type": "string"}},
                        "search_mode": {"type": "string", "enum": ["hybrid", "lexical"]},
                        "limit": {"type": "integer"},
                    },
                    "required": ["project_id", "scope_mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_semantic_read_model",
                "description": "按 graph_set_id 与 model_name 精确读取只读模型"
                "（table-mapping-detail/join-mapping-detail/enum-meaning-detail/"
                "metric-detail 等，可用 entity 指定资源 IRI）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "graph_set_id": {"type": "string"},
                        "model_name": {"type": "string"},
                        "entity_iri": {"type": "string"},
                        "include": {"type": "string"},
                    },
                    "required": ["graph_set_id", "model_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": SQL_TOOL,
                "description": "对业务数据库执行单条只读 SQL（仅 SELECT），"
                "返回列与行或数据库错误。",
                "parameters": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}},
                    "required": ["sql"],
                },
            },
        },
    ]


# ---------------------------------------------------------------------------
# Round execution
# ---------------------------------------------------------------------------


async def _runtime_context(mcp: McpSession) -> tuple[str, str]:
    """Authorized semantic context straight from the runtime discovery result."""
    try:
        text = await mcp.call("discover_semantic_scopes", {"query": "", "limit": 50})
    except Exception as exc:  # recorded truthfully; the round continues
        return f"discover_semantic_scopes 调用失败：{exc}", "error"
    return text[:MAX_DISCOVERY_CHARS] or "（discover_semantic_scopes 返回为空）", "ok"


async def run_round(
    round_def: dict[str, Any],
    *,
    llm_base_url: str,
    llm_api_key: str,
    llm_model: str,
    max_turns: int,
    client_factory: Any | None = None,
    mcp_session_factory: Any | None = None,
    execute_sql_fn: Any | None = None,
) -> dict[str, Any]:
    """Run one round. The three ``*_factory``/``_fn`` keywords are controlled
    fixtures for the mechanical tests; the CLI always uses the defaults."""
    import httpx

    if client_factory is None:

        def client_factory():
            return httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS)

    if mcp_session_factory is None:
        mcp_session_factory = McpSession
    if execute_sql_fn is None:
        execute_sql_fn = run_execute_sql

    api_key = os.environ[round_def["principal_env"]]
    transcript: list[dict[str, Any]] = []
    executed_sql: list[dict[str, Any]] = []
    question = round_def["question"]

    async with mcp_session_factory(api_key) as mcp:
        allowed = await mcp.narrowed_tool_names()
        missing = [name for name in ALLOWED_MCP_TOOLS if name not in allowed]
        if missing:
            raise DriverError(f"MCP server did not expose required tools: {missing}")
        runtime_context, context_status = await _runtime_context(mcp)
        messages = build_messages(question, runtime_context)
        transcript.extend(messages)

        answer = ""
        interaction_reason = "max_turns_exhausted"
        turns_used = 0
        async with client_factory() as client:
            for turn in range(max_turns):
                turns_used = turn + 1
                response = await client.post(
                    f"{llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {llm_api_key}"},
                    json={
                        "model": llm_model,
                        "messages": messages,
                        "tools": _llm_tools(),
                        "temperature": 0,
                    },
                )
                if response.status_code != 200:
                    raise DriverError(
                        f"LLM request failed: {response.status_code} {response.text[:400]}"
                    )
                choice = response.json()["choices"][0]["message"]
                if choice.get("content"):
                    transcript.append({"role": "assistant", "content": choice["content"]})
                tool_calls = choice.get("tool_calls") or []
                if not tool_calls:
                    answer = choice.get("content") or ""
                    interaction_reason = "answered"
                    break
                messages.append(choice)
                for call in tool_calls:
                    name = call["function"]["name"]
                    try:
                        arguments = json.loads(call["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    if name == SQL_TOOL:
                        sql = str(arguments.get("sql", ""))
                        payload = execute_sql_fn(sql)
                        executed_sql.append(
                            {"sql": sql, "adapter_output": payload}
                        )
                        result_text = json.dumps(payload, ensure_ascii=False)
                    elif name in ALLOWED_MCP_TOOLS:
                        result_text = await mcp.call(name, arguments)
                    else:
                        result_text = f"error: tool {name} is not available"
                    transcript.append(
                        {
                            "role": "tool",
                            "tool": name,
                            "arguments": arguments,
                            "result": result_text[:MAX_TOOL_RESULT_CHARS],
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": result_text[:MAX_TOOL_RESULT_CHARS],
                        }
                    )
            else:
                answer = answer or "（达到最大轮次，未给出最终回答）"

    record = {
        "question_id": round_def["question_id"],
        "principal": round_def["principal_name"],
        "principal_env": round_def["principal_env"],
        "question": question,
        "runtime_completion": {
            "completed": interaction_reason == "answered" and context_status == "ok",
            "reason": (
                "answered"
                if interaction_reason == "answered" and context_status == "ok"
                else (
                    "semantic_discovery_failed"
                    if context_status != "ok"
                    else interaction_reason
                )
            ),
            "interaction_reason": interaction_reason,
            "semantic_discovery": context_status,
            "turns_used": turns_used,
            "max_turns": max_turns,
        },
        "runtime_context_status": context_status,
        "runtime_context": runtime_context,
        "answer": answer,
        "executed_sql": executed_sql,
        "transcript": transcript,
        "row_comparison": judge_sql_rows(round_def, executed_sql),
    }
    record["protection"] = check_protection(round_def, record)
    record["answer_evidence"] = collect_answer_evidence(round_def, record)
    record["verdict"] = judge_round(round_def, record)
    record["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return record


def _failure_record(
    round_def: dict[str, Any], exc: Exception, redactions: list[str]
) -> dict[str, Any]:
    """Keep the evidence for a round that could not run (runtime/infrastructure)."""
    return _redact(
        {
            "question_id": round_def["question_id"],
            "principal": round_def["principal_name"],
            "principal_env": round_def["principal_env"],
            "question": round_def["question"],
            "failure_layer": "runtime/infrastructure",
            "failure_reason": f"{exc.__class__.__name__}: {exc}",
            "runtime_completion": {
                "completed": False,
                "reason": "round_error",
                "turns_used": 0,
            },
            "answer": "",
            "executed_sql": [],
            "transcript": [],
            "row_comparison": {"verdict": "not_executed", "reason": "round did not run"},
            "protection": {
                "verdict": "not_verified",
                "role": "protection conclusions only; can only produce FAIL",
                "checks": [],
            },
            "answer_evidence": {"role": "evidence_only", "points": []},
            "verdict": {
                "question_id": round_def["question_id"],
                "passed": False,
                "runtime_completion": "round_error",
                "sql_rows_verdict": "not_executed",
                "protection_verdict": "not_verified",
                "answer_evidence_role": "evidence_only (excluded from verdicts)",
            },
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        redactions,
    )


def _redact(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "***REDACTED***")
        return value
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item, secrets) for key, item in value.items()}
    return value


# ---------------------------------------------------------------------------
# Environment reporting (--check): status only, never a PASS claim
# ---------------------------------------------------------------------------


def _env_status(name: str) -> dict[str, str]:
    value = os.environ.get(name)
    return {
        "name": name,
        "status": "ok" if value else "missing",
        "detail": "" if value else "environment variable is not set",
    }


def adapter_contract_status(env: dict[str, str] | None = None) -> dict[str, str]:
    """Probe the frozen adapter contract with a schema-free statement."""
    payload = run_execute_sql("SELECT 1", env=env)
    error = payload.get("error") or {}
    if payload.get("ok") is False and error.get("kind") == "config_error":
        return {
            "name": "adapter_contract",
            "status": "blocked_by_missing_dsn",
            "detail": f"adapter reports config_error: {error.get('message', '')}",
        }
    if payload.get("ok") is False and error.get("kind") == "driver_error":
        return {
            "name": "adapter_contract",
            "status": "error",
            "detail": str(error.get("message", ""))[:400],
        }
    if payload.get("ok") is False:
        return {
            "name": "adapter_contract",
            "status": "error",
            "detail": f"adapter error {error.get('kind')}: {error.get('message', '')}",
        }
    return {
        "name": "adapter_contract",
        "status": "ok",
        "detail": f"adapter SELECT 1 ok (columns={payload.get('columns')})",
    }


def backend_health_status(backend_url: str) -> dict[str, str]:
    try:
        import httpx
    except ImportError as exc:
        return {"name": "backend_health", "status": "error", "detail": f"httpx unavailable: {exc}"}
    try:
        response = httpx.get(f"{backend_url}/api/health", timeout=10)
    except Exception as exc:
        return {
            "name": "backend_health",
            "status": "unreachable",
            "detail": f"{backend_url}/api/health: {exc.__class__.__name__}: {exc}",
        }
    if response.status_code != 200:
        return {
            "name": "backend_health",
            "status": "unhealthy",
            "detail": f"{backend_url}/api/health returned {response.status_code}",
        }
    return {"name": "backend_health", "status": "ok", "detail": backend_url}


async def tool_surface_status(api_key: str | None, credential_env: str | None) -> dict[str, str]:
    if not api_key:
        return {
            "name": "mcp_tool_surface",
            "status": "not_verified",
            "detail": "requires backend health and one principal credential",
        }
    try:
        async with McpSession(api_key) as mcp:
            allowed = await mcp.narrowed_tool_names()
    except Exception as exc:
        return {
            "name": "mcp_tool_surface",
            "status": "error",
            "detail": f"probing with {credential_env}: {exc.__class__.__name__}: {exc}",
        }
    missing = [name for name in ALLOWED_MCP_TOOLS if name not in allowed]
    if missing:
        return {
            "name": "mcp_tool_surface",
            "status": "error",
            "detail": f"MCP server did not expose required tools: {missing}",
        }
    return {
        "name": "mcp_tool_surface",
        "status": "ok",
        "detail": f"as {credential_env}: narrowed tools = {allowed} + local {SQL_TOOL}",
    }


async def check_mode(rounds_path: Path | None, backend_url: str) -> int:
    items: list[dict[str, Any]] = []

    principal_envs = list(DEFAULT_PRINCIPAL_ENVS)
    if rounds_path is None:
        items.append(
            {
                "name": "rounds_file",
                "status": "not_provided",
                "detail": "--rounds is required for run mode; --check validated no file",
            }
        )
    else:
        try:
            rounds = load_rounds(rounds_path)
        except RoundsFileError as exc:
            items.append({"name": "rounds_file", "status": "error", "detail": str(exc)})
        else:
            principal_envs = sorted({entry["principal_env"] for entry in rounds})
            items.append(
                {
                    "name": "rounds_file",
                    "status": "ok",
                    "detail": (
                        f"{rounds_path} -> {len(rounds)} round(s), "
                        f"principals={principal_envs}"
                    ),
                }
            )

    credentials = [_env_status(name) for name in principal_envs]
    items.extend(credentials)
    dsn = _env_status(DSN_ENV)
    items.append(
        {**dsn, "detail": (dsn["detail"] + f" (the adapter reads only {DSN_ENV})")}
    )
    items.append(adapter_contract_status())
    items.append(backend_health_status(backend_url))
    first_credential = os.environ.get(principal_envs[0]) if principal_envs else None
    first_credential_env = principal_envs[0] if principal_envs else None
    items.append(await tool_surface_status(first_credential, first_credential_env))
    items.extend(
        [
            _env_status(LLM_BASE_ENV),
            _env_status(LLM_KEY_ENV),
            _env_status(LLM_MODEL_ENV),
        ]
    )

    for item in items:
        detail = f" — {item['detail']}" if item["detail"] else ""
        print(f"{item['name']}: {item['status']}{detail}")

    unsatisfied = [
        item for item in items if item["status"] not in ("ok", "not_provided")
    ]
    if unsatisfied:
        print("readiness: NOT READY — nothing executed")
        print(
            "未执行任何 Consumer 轮次，未执行任何真实 SQL 验收；"
            "--check 只如实报告配置状态。"
        )
        return 1
    print("readiness: READY — 环境齐备；--check 本身不执行任何轮次")
    print(
        "未执行任何 Consumer 轮次，未执行任何真实 SQL 验收；"
        "真实轮次需 --rounds 与用户 R3.0-006 授权。"
    )
    return 0


# ---------------------------------------------------------------------------
# Run mode
# ---------------------------------------------------------------------------


def _required_env(names: list[str]) -> dict[str, str]:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise DriverError(
            f"missing required environment variables: {missing}; nothing was executed"
        )
    return {name: os.environ[name] for name in names}


async def run_mode(
    rounds: list[dict[str, Any]],
    out_dir: Path,
    only: list[str] | None,
    backend_url: str,
) -> int:
    env = _required_env(
        [LLM_BASE_ENV, LLM_KEY_ENV, LLM_MODEL_ENV, DSN_ENV]
        + sorted({entry["principal_env"] for entry in rounds})
    )
    health = backend_health_status(backend_url)
    if health["status"] != "ok":
        raise DriverError(f"backend is not healthy: {health['detail']}; nothing was executed")
    max_turns = int(os.environ.get(MAX_TURNS_ENV, str(DEFAULT_MAX_TURNS)))
    redactions = [
        env[LLM_KEY_ENV],
        env[DSN_ENV],
        *(os.environ[name] for name in sorted({entry["principal_env"] for entry in rounds})),
    ]

    selected = rounds
    if only:
        known = {entry["question_id"] for entry in rounds}
        unknown = [item for item in only if item not in known]
        if unknown:
            raise DriverError(f"unknown question_id(s) in --only: {unknown}")
        selected = [entry for entry in rounds if entry["question_id"] in set(only)]

    out_dir.mkdir(parents=True, exist_ok=True)
    verdicts = []
    for round_def in selected:
        print(f"running {round_def['question_id']} ({round_def['principal_name']}) ...")
        try:
            record = await run_round(
                round_def,
                llm_base_url=env[LLM_BASE_ENV],
                llm_api_key=env[LLM_KEY_ENV],
                llm_model=env[LLM_MODEL_ENV],
                max_turns=max_turns,
            )
        except Exception as exc:  # keep the evidence, keep going
            record = _failure_record(round_def, exc, redactions)
            print(f"  -> round failed to run: {record['failure_reason']}")
        record = _redact(record, redactions)
        verdict = record["verdict"]
        verdicts.append(verdict)
        path = out_dir / f"{round_def['question_id']}-{round_def['principal_name']}.json"
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        status = "PASS" if verdict["passed"] else "FAIL"
        print(f"  -> {status} ({path})")
        if not verdict["passed"]:
            print(f"     completion: {verdict['runtime_completion']}")
            print(f"     sql_rows: {verdict['sql_rows_verdict']}")
            print(f"     protection: {verdict['protection_verdict']}")
            comparison = record["row_comparison"]
            reason = comparison.get("detail") or comparison.get("reason")
            if reason:
                print(f"     rows: {reason}")

    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "rounds": verdicts,
                "all_passed": all(entry["passed"] for entry in verdicts),
                "note": (
                    "SQL 正确性由 expected_rows 与 adapter 实际行的归一化比较决定；"
                    "答案措辞仅为展示性证据。本文件不构成真实授权下的语义或数据安全结论。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"summary: {summary_path}")
    return 0 if all(entry["passed"] for entry in verdicts) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R3.0-006 externalized Consumer rounds driver (design §3.G6)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment: R3006_SMOKE_KEY_* (per round principal_env), "
            f"{DSN_ENV}, R3006_SMOKE_LLM_BASE_URL/_API_KEY/_MODEL, "
            f"{BACKEND_URL_ENV}, {MAX_TURNS_ENV}.\n"
            "--check reports configuration status only and executes nothing."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report environment/configuration status truthfully; execute nothing",
    )
    parser.add_argument(
        "--rounds",
        default=None,
        help="path to the external rounds JSON file (required for run mode)",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated question_id values to run (default: all rounds)",
    )
    parser.add_argument(
        "--evidence-dir",
        default=str(DEFAULT_EVIDENCE_DIR),
        help="transcript output directory",
    )
    parser.add_argument(
        "--backend-url",
        default=None,
        help=f"override {BACKEND_URL_ENV} (default {DEFAULT_BACKEND_URL})",
    )
    args = parser.parse_args(argv)
    backend_url = args.backend_url or os.environ.get(BACKEND_URL_ENV, DEFAULT_BACKEND_URL)

    try:
        if args.check:
            rounds_path = Path(args.rounds) if args.rounds else None
            return asyncio.run(check_mode(rounds_path, backend_url))
        if not args.rounds:
            parser.error("--rounds is required unless --check is given")
        rounds = load_rounds(Path(args.rounds))
        only = [item.strip() for item in args.only.split(",")] if args.only else None
        return asyncio.run(run_mode(rounds, Path(args.evidence_dir), only, backend_url))
    except RoundsFileError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    except DriverError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
