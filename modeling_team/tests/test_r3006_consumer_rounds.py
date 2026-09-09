"""R3.0-006 G6 Consumer driver regression tests (design §3.G6, test plan T-G6).

Covers, without any live LLM, real modeling start, or authorized SQL round:

- T-G6-2: the external rounds file's expected answers/rows and protected
  assertions never enter a Consumer prompt, and the driver/prompt carries no
  scenario-specific wording.
- T-G6-3: the round verdict is decided by the row-level comparison of the
  actual adapter rows against ``expected_rows`` (equal / row-order / value
  type / missing column), while natural-language answer wording stays
  evidence-only.
- T-G6-4: ``execute_sql`` shells out to the frozen
  ``scripts/r3-0-005/sql_exec_adapter.py`` and preserves its error contract,
  including the missing-DSN ``config_error`` path.
- T-G6-1 (configuration-status part): ``--help`` and ``--check`` are usable
  before any authorization, ``--check`` truthfully lists missing items, exits
  non-zero, and never claims a real SQL acceptance PASS.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER_PATH = REPO_ROOT / "scripts" / "r3-0-006" / "consumer_rounds.py"
ADAPTER_PATH = REPO_ROOT / "scripts" / "r3-0-005" / "sql_exec_adapter.py"
DSN_ENV = "R3005_SQL_ADAPTER_DSN"

SECRET_ROW = "sentinel-expected-row-4f3a"
SECRET_POINT = "sentinel-answer-point-9c21"
SECRET_PROTECTED = "sentinel-protected-token-77b0"


def _load_driver():
    spec = importlib.util.spec_from_file_location("r3006_consumer_rounds_under_test", DRIVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver():
    return _load_driver()


driver_module = _load_driver()


def _write_rounds(tmp_path: Path, rounds: list[dict], **top_level) -> Path:
    path = tmp_path / "rounds.json"
    path.write_text(
        json.dumps({**top_level, "rounds": rounds}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _isolation_round() -> dict:
    return {
        "question_id": "CQ-ISOLATION-01",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "按已授权口径统计本月相关单据数量",
        "expected_rows": [[SECRET_ROW, "7"]],
        "expected_columns": ["name", "total"],
        "expected_answer_points": [SECRET_POINT],
        "protected": {"forbidden_in_sql": [SECRET_PROTECTED]},
    }


# ------------------------------------------------------------- rounds contract


def test_rounds_file_rejects_unknown_and_invalid_definitions(driver, tmp_path) -> None:
    bad_unknown = _write_rounds(
        tmp_path, [dict(_isolation_round(), extra_field="x")], description="d"
    )
    with pytest.raises(driver.RoundsFileError, match="unknown fields"):
        driver.load_rounds(bad_unknown)

    bad_missing = _write_rounds(tmp_path, [{"question_id": "Q1"}])
    with pytest.raises(driver.RoundsFileError, match="missing fields"):
        driver.load_rounds(bad_missing)

    duplicate = _isolation_round()
    with pytest.raises(driver.RoundsFileError, match="duplicates"):
        driver.load_rounds(_write_rounds(tmp_path, [duplicate, duplicate]))

    bad_protected = _write_rounds(
        tmp_path, [dict(_isolation_round(), protected={"expected_rows": []})]
    )
    with pytest.raises(driver.RoundsFileError, match="protected has unknown fields"):
        driver.load_rounds(bad_protected)

    bad_rows = _write_rounds(tmp_path, [dict(_isolation_round(), expected_rows=[{"a": 1}])])
    with pytest.raises(driver.RoundsFileError, match="expected_rows\\[0\\] must be a list"):
        driver.load_rounds(bad_rows)

    bad_top = tmp_path / "bad-top.json"
    bad_top.write_text(json.dumps({"items": []}), encoding="utf-8")
    with pytest.raises(driver.RoundsFileError, match="unknown top-level fields"):
        driver.load_rounds(bad_top)


def test_rounds_file_loads_minimal_round(driver, tmp_path) -> None:
    path = _write_rounds(
        tmp_path,
        [
            {
                "question_id": "CQ-02",
                "principal_env": "R3006_SMOKE_KEY_NOGRANT",
                "question": "未授权的问题",
                "protected": {"require_no_sql": True, "require_unconfirmable": True},
            }
        ],
    )
    rounds = driver.load_rounds(path)
    assert len(rounds) == 1
    entry = rounds[0]
    assert entry["expected_rows"] is None
    assert entry["expected_columns"] is None
    assert entry["expected_rows_order_matters"] is False
    assert entry["protected"] == {"require_no_sql": True, "require_unconfirmable": True}


# ----------------------------------------- T-G6-2: prompt / expected-data wall


def test_expected_data_never_enters_prompt(driver, tmp_path) -> None:
    entry = _isolation_round()
    runtime_context = "runtime-authorized-scope-digest:dynamic-discovery-result"
    messages = driver.build_messages(entry["question"], runtime_context)
    blob = json.dumps(messages, ensure_ascii=False)

    # Only the question and the runtime discovery context may appear.
    assert entry["question"] in blob
    assert runtime_context in blob
    # Expected rows, columns, answer points and protected terms stay driver-side.
    for secret in (SECRET_ROW, SECRET_POINT, SECRET_PROTECTED):
        assert secret not in blob
    for field in ("expected_rows", "expected_columns", "expected_answer_points", "protected"):
        assert field not in blob

    # The same secrets are not embedded in the driver source either: the file
    # above is the only place the expected data exists.
    source = DRIVER_PATH.read_text(encoding="utf-8")
    for secret in (SECRET_ROW, SECRET_POINT, SECRET_PROTECTED):
        assert secret not in source


def test_system_prompt_and_tool_surface_are_generic(driver) -> None:
    source = DRIVER_PATH.read_text(encoding="utf-8")
    for scenario_term in (
        "工单",
        "备件",
        "标准成本",
        "仓库",
        "库存",
        "设备型号",
        "industrial_service_v3",
        "work_orders",
        "RESOLVED",
    ):
        assert scenario_term not in source
    assert "无法确认" in driver.SYSTEM_PROMPT


# --------------------------------------- T-G6-3: row-level comparison verdicts


def _compare(driver, expected_rows, actual_rows, *, columns=None, actual_columns=None, order=False):
    return driver.compare_rows(
        expected_rows=expected_rows,
        expected_columns=columns,
        actual_columns=actual_columns if actual_columns is not None else (columns or []),
        actual_rows=actual_rows,
        order_matters=order,
    )


def test_row_comparison_equal_rows_pass(driver) -> None:
    result = _compare(
        driver,
        [["alpha", 3], ["beta", "12.50"]],
        [["alpha", 3], ["beta", "12.50"]],
        columns=["name", "total"],
    )
    assert result["verdict"] == "pass"
    assert result["column_check"]["pass"] is True


def test_row_comparison_json_numbers_compare_numerically(driver) -> None:
    assert _compare(driver, [[3]], [[3.0]], columns=["count"])["verdict"] == "pass"


def test_row_comparison_row_order_difference(driver) -> None:
    expected = [["alpha", 1], ["beta", 2]]
    actual = [["beta", 2], ["alpha", 1]]
    insensitive = _compare(driver, expected, actual, columns=["name", "total"])
    assert insensitive["verdict"] == "pass"
    assert insensitive["row_compare"]["mode"] == "multiset"

    sensitive = _compare(driver, expected, actual, columns=["name", "total"], order=True)
    assert sensitive["verdict"] == "fail"
    assert sensitive["row_compare"]["mode"] == "sequence"
    assert sensitive["row_compare"]["first_difference"]["row_index"] == 0


def test_row_comparison_value_type_difference_fails(driver) -> None:
    # number 5 vs the text "5" is a class difference under the 005 contract
    result = _compare(driver, [[5]], [["5"]], columns=["count"])
    assert result["verdict"] == "fail"

    # bool true vs number 1 is a class difference, never collapsed
    result = _compare(driver, [[True]], [[1]], columns=["flag"])
    assert result["verdict"] == "fail"

    # null vs the literal text NULL is a class difference
    result = _compare(driver, [[None]], [["NULL"]], columns=["reason"])
    assert result["verdict"] == "fail"


def test_row_comparison_preserves_json_strings_exactly(driver) -> None:
    # a zero-padded identifier must not equate to a different literal
    result = _compare(driver, [["001"]], [["1"]], columns=["code"])
    assert result["verdict"] == "fail"

    # nor may sign or spelling variants of numeric-looking text collapse
    result = _compare(driver, [["1"]], [["+1"]], columns=["code"])
    assert result["verdict"] == "fail"

    # decimal text keeps its exact serialized form (no scale equivalence)
    result = _compare(driver, [["12.50"]], [["12.5"]], columns=["amount"])
    assert result["verdict"] == "fail"


def test_row_comparison_missing_column_fails(driver) -> None:
    result = _compare(
        driver,
        [["alpha", 3]],
        [["alpha", 3]],
        columns=["name", "total"],
        actual_columns=["name"],
    )
    assert result["verdict"] == "fail"
    assert result["column_check"]["pass"] is False
    assert "column mismatch" in result["detail"]


def test_row_comparison_empty_and_count_mismatch(driver) -> None:
    assert _compare(driver, [], [], columns=["name"])["verdict"] == "pass"
    result = _compare(driver, [["alpha"], ["beta"]], [["alpha"]], columns=["name"])
    assert result["verdict"] == "fail"
    assert "row count differs" in result["detail"]


def _record_for_judgement(driver, *, answer: str, row_verdict: str, executed_sql=None) -> dict:
    comparison = {"verdict": row_verdict}
    if row_verdict == "fail":
        comparison["detail"] = "row count differs: expected 1, actual 0"
    protection = driver.check_protection(
        {"protected": {}}, {"executed_sql": executed_sql or [], "answer": answer}
    )
    return {"answer": answer, "row_comparison": comparison, "protection": protection}


def test_answer_wording_cannot_make_rows_pass(driver) -> None:
    round_def = {
        "question_id": "CQ-JUDGE-01",
        "expected_answer_points": ["口径", "已完成"],
        "protected": {},
    }
    record = _record_for_judgement(
        driver, answer="口径是已完成状态计数，结果是 42。", row_verdict="fail"
    )
    record["answer_evidence"] = driver.collect_answer_evidence(round_def, record)
    record["verdict"] = driver.judge_round(round_def, record)

    # The answer wording matches every expected point, yet the round must FAIL:
    # only the row comparison decides SQL correctness.
    assert all(point["present"] for point in record["answer_evidence"]["points"])
    assert record["verdict"]["passed"] is False
    assert record["verdict"]["sql_rows_verdict"] == "fail"


def test_round_without_expected_rows_is_structural_only(driver) -> None:
    round_def = {
        "question_id": "CQ-JUDGE-02",
        "expected_rows": None,
        "expected_answer_points": [],
        "protected": {"require_no_sql": True, "require_unconfirmable": True},
    }
    record = {
        "answer": "无法确认",
        "runtime_completion": {"completed": True, "reason": "answered"},
        "row_comparison": {"verdict": "not_applicable"},
        "executed_sql": [],
    }
    record["protection"] = driver.check_protection(round_def, record)
    record["verdict"] = driver.judge_round(round_def, record)
    assert record["verdict"]["passed"] is True

    leaking = dict(record, executed_sql=[{"sql": "SELECT secret_count FROM t"}])
    leaking["protection"] = driver.check_protection(round_def, leaking)
    leaking["verdict"] = driver.judge_round(round_def, leaking)
    assert leaking["verdict"]["passed"] is False
    assert leaking["verdict"]["protection_verdict"] == "fail"


def test_incomplete_interaction_cannot_pass(driver) -> None:
    round_def = {
        "question_id": "CQ-JUDGE-03",
        "expected_rows": [["a", 1]],
        "expected_answer_points": [],
        "protected": {},
        "expected_rows_order_matters": False,
    }
    record = {
        "answer": "（达到最大轮次，未给出最终回答）",
        "runtime_completion": {"completed": False, "reason": "max_turns_exhausted"},
        "row_comparison": driver.judge_sql_rows(
            round_def,
            [
                {
                    "sql": "s",
                    "adapter_output": {"ok": True, "columns": ["a", "b"], "rows": [["a", 1]]},
                }
            ],
        ),
        "executed_sql": [],
    }
    record["protection"] = driver.check_protection(round_def, record)
    record["verdict"] = driver.judge_round(round_def, record)
    # the SQL rows did match, yet the exhausted interaction is not a round PASS
    assert record["verdict"]["sql_rows_verdict"] == "pass"
    assert record["verdict"]["runtime_completion"] == "max_turns_exhausted"
    assert record["verdict"]["passed"] is False


# ------------- controlled tool-loop fixtures (no live LLM, no real database)


class _FakeMcpSession:
    """Minimal authorized-context stand-in for the driver's MCP seam."""

    def __init__(self, scopes_text: str):
        self._scopes_text = scopes_text
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return None

    async def narrowed_tool_names(self):
        return list(driver_module.ALLOWED_MCP_TOOLS)

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        assert name in driver_module.ALLOWED_MCP_TOOLS
        return self._scopes_text


class _FakeAdapter:
    """Scripted rows per SQL text; records every statement it was asked to run."""

    def __init__(self, results: dict[str, dict]):
        self._results = results
        self.executed: list[str] = []

    def __call__(self, sql: str, **_kwargs):
        self.executed.append(sql)
        return self._results[sql]


def _scripted_llm(responses: list[dict]):
    """httpx MockTransport serving one scripted OpenAI response per request."""
    state = {"index": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        index = state["index"]
        state["index"] = index + 1
        assert index < len(responses), "scripted LLM responses exhausted"
        return httpx.Response(200, json={"choices": [{"message": responses[index]}]})

    return httpx.MockTransport(handler)


def _run_round(
    driver, round_def, responses, adapter, max_turns=6, session_factory=None
):
    principal_env = round_def["principal_env"]
    previous = os.environ.get(principal_env)
    os.environ[principal_env] = "test-principal-key"
    if session_factory is None:
        session_factory = lambda key: _FakeMcpSession("runtime-scope-digest")  # noqa: E731
    try:
        return asyncio.run(
            driver.run_round(
                round_def,
                llm_base_url="http://llm.test/v1",
                llm_api_key="test-key",
                llm_model="test-model",
                max_turns=max_turns,
                client_factory=lambda: httpx.AsyncClient(
                    transport=_scripted_llm(responses)
                ),
                mcp_session_factory=session_factory,
                execute_sql_fn=adapter,
            )
        )
    finally:
        if previous is None:
            os.environ.pop(principal_env, None)
        else:
            os.environ[principal_env] = previous


_TOOL_CALL_SEQ = {"index": 0}


def _tool_call(name: str, **arguments) -> dict:
    _TOOL_CALL_SEQ["index"] += 1
    return {
        "tool_calls": [
            {
                "id": f"call-{_TOOL_CALL_SEQ['index']}",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments),
                },
            }
        ]
    }


def test_tool_loop_wrong_then_correct_final_result_passes(driver) -> None:
    round_def = {
        "question_id": "CQ-LOOP-01",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "按已授权口径统计数量",
        "expected_rows": [["right", 2]],
        "expected_columns": ["name", "total"],
        "expected_answer_points": [],
        "protected": {},
        "expected_rows_order_matters": False,
    }
    adapter = _FakeAdapter(
        {
            "SELECT wrong": {"ok": True, "columns": ["name", "total"], "rows": [["wrong", 1]]},
            "SELECT right": {"ok": True, "columns": ["name", "total"], "rows": [["right", 2]]},
        }
    )
    record = _run_round(
        driver,
        round_def,
        [
            _tool_call(driver.SQL_TOOL, sql="SELECT wrong"),
            _tool_call(driver.SQL_TOOL, sql="SELECT right"),
            {"content": "口径是……，答案是 2。"},
        ],
        adapter,
    )

    assert record["runtime_completion"] == {
        "completed": True,
        "reason": "answered",
        "interaction_reason": "answered",
        "semantic_discovery": "ok",
        "turns_used": 3,
        "max_turns": 6,
    }
    # every attempt stays as evidence, and the FINAL attempt is the judged one
    assert adapter.executed == ["SELECT wrong", "SELECT right"]
    assert len(record["executed_sql"]) == 2
    comparison = record["row_comparison"]
    assert comparison["verdict"] == "pass"
    assert comparison["judged_attempt_index"] == 1
    assert comparison["final_sql"] == "SELECT right"
    assert record["verdict"]["passed"] is True


def test_tool_loop_correct_then_wrong_final_result_fails(driver) -> None:
    round_def = {
        "question_id": "CQ-LOOP-02",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "按已授权口径统计数量",
        "expected_rows": [["right", 2]],
        "expected_columns": ["name", "total"],
        "expected_answer_points": ["口径是"],
        "protected": {},
        "expected_rows_order_matters": False,
    }
    adapter = _FakeAdapter(
        {
            "SELECT right": {"ok": True, "columns": ["name", "total"], "rows": [["right", 2]]},
            "SELECT wrong": {"ok": True, "columns": ["name", "total"], "rows": [["wrong", 1]]},
        }
    )
    record = _run_round(
        driver,
        round_def,
        [
            _tool_call(driver.SQL_TOOL, sql="SELECT right"),
            _tool_call(driver.SQL_TOOL, sql="SELECT wrong"),
            {"content": "口径是……"},
        ],
        adapter,
    )

    comparison = record["row_comparison"]
    assert comparison["verdict"] == "fail"
    assert comparison["judged_attempt_index"] == 1
    # an earlier successful attempt is never used as a fallback
    assert len(record["executed_sql"]) == 2
    assert record["verdict"]["passed"] is False


def test_tool_loop_final_adapter_error_is_not_fallback_passed(driver) -> None:
    round_def = {
        "question_id": "CQ-LOOP-03",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "按已授权口径统计数量",
        "expected_rows": [["right", 2]],
        "expected_columns": ["name", "total"],
        "expected_answer_points": [],
        "protected": {},
        "expected_rows_order_matters": False,
    }
    adapter = _FakeAdapter(
        {
            "SELECT right": {"ok": True, "columns": ["name", "total"], "rows": [["right", 2]]},
            "SELECT broken": {
                "ok": False,
                "error": {"kind": "database_error", "message": "column missing"},
                "adapter_exit_code": 1,
            },
        }
    )
    record = _run_round(
        driver,
        round_def,
        [
            _tool_call(driver.SQL_TOOL, sql="SELECT right"),
            _tool_call(driver.SQL_TOOL, sql="SELECT broken"),
            {"content": "答案 2。"},
        ],
        adapter,
    )

    comparison = record["row_comparison"]
    assert comparison["verdict"] == "adapter_error"
    assert comparison["adapter_error"]["kind"] == "database_error"
    assert comparison["judged_attempt_index"] == 1
    assert record["verdict"]["passed"] is False


def test_tool_loop_no_sql_cannot_pass_expected_empty_rows(driver) -> None:
    round_def = {
        "question_id": "CQ-LOOP-04",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "未发生任何业务时的计数",
        "expected_rows": [],
        "expected_columns": ["total"],
        "expected_answer_points": [],
        "protected": {},
        "expected_rows_order_matters": False,
    }
    record = _run_round(driver, round_def, [{"content": "答案是 0 条。"}], _FakeAdapter({}))

    comparison = record["row_comparison"]
    assert comparison["verdict"] == "not_executed"
    assert record["verdict"]["passed"] is False


def test_tool_loop_successful_empty_result_passes_expected_empty_rows(driver) -> None:
    round_def = {
        "question_id": "CQ-LOOP-05",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "未发生任何业务时的计数",
        "expected_rows": [],
        "expected_columns": ["total"],
        "expected_answer_points": [],
        "protected": {},
        "expected_rows_order_matters": False,
    }
    adapter = _FakeAdapter(
        {"SELECT empty": {"ok": True, "columns": ["total"], "rows": []}}
    )
    record = _run_round(
        driver,
        round_def,
        [_tool_call(driver.SQL_TOOL, sql="SELECT empty"), {"content": "答案 0 条。"}],
        adapter,
    )

    comparison = record["row_comparison"]
    assert comparison["verdict"] == "pass"
    assert comparison["judged_attempt_index"] == 0
    assert record["verdict"]["passed"] is True


def test_tool_loop_exhausted_turns_keeps_row_evidence_but_fails_round(driver) -> None:
    round_def = {
        "question_id": "CQ-LOOP-06",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "按已授权口径统计数量",
        "expected_rows": [["right", 2]],
        "expected_columns": ["name", "total"],
        "expected_answer_points": [],
        "protected": {},
        "expected_rows_order_matters": False,
    }
    adapter = _FakeAdapter(
        {"SELECT right": {"ok": True, "columns": ["name", "total"], "rows": [["right", 2]]}}
    )
    record = _run_round(
        driver,
        round_def,
        [
            _tool_call(driver.SQL_TOOL, sql="SELECT right"),
            _tool_call(driver.SQL_TOOL, sql="SELECT right"),
        ],
        adapter,
        max_turns=2,
    )

    assert record["runtime_completion"]["completed"] is False
    assert record["runtime_completion"]["reason"] == "max_turns_exhausted"
    assert record["row_comparison"]["verdict"] == "pass"  # evidence stays visible
    assert record["verdict"]["passed"] is False


def test_tool_loop_prompt_carries_only_question_and_runtime_context(driver) -> None:
    round_def = {
        "question_id": "CQ-LOOP-07",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "按已授权口径统计数量",
        "expected_rows": [[SECRET_ROW, "2"]],
        "expected_columns": ["name", "total"],
        "expected_answer_points": [SECRET_POINT],
        "protected": {"forbidden_in_sql": [SECRET_PROTECTED]},
        "expected_rows_order_matters": False,
    }
    adapter = _FakeAdapter(
        {"SELECT right": {"ok": True, "columns": ["name", "total"], "rows": [[SECRET_ROW, 2]]}}
    )
    record = _run_round(
        driver,
        round_def,
        [_tool_call(driver.SQL_TOOL, sql="SELECT right"), {"content": "答案。"}],
        adapter,
    )

    prompt_blob = json.dumps(record["transcript"][:2], ensure_ascii=False)
    assert round_def["question"] in prompt_blob
    assert "runtime-scope-digest" in prompt_blob
    for secret in (SECRET_ROW, SECRET_POINT, SECRET_PROTECTED):
        assert secret not in prompt_blob
    # expected data lives only in the driver-side judgment sections
    judgment_blob = json.dumps(record["row_comparison"], ensure_ascii=False)
    assert SECRET_ROW in judgment_blob


def test_round_without_any_oracle_is_rejected_and_never_passes(driver, tmp_path) -> None:
    # a typed input error at load time: nothing can be evaluated
    path = _write_rounds(
        tmp_path,
        [
            {
                "question_id": "CQ-NO-ORACLE",
                "principal_env": "R3006_SMOKE_KEY_GRANT",
                "question": "没有任何判定依据的问题",
            }
        ],
    )
    with pytest.raises(driver.RoundsFileError, match="no oracle"):
        driver.load_rounds(path)

    # defensive: even a hand-built record cannot PASS without an oracle
    round_def = {"question_id": "CQ-NO-ORACLE", "expected_answer_points": []}
    record = {
        "answer": "答案。",
        "runtime_completion": {"completed": True, "reason": "answered"},
        "row_comparison": {"verdict": "not_applicable"},
        "executed_sql": [],
    }
    record["protection"] = driver.check_protection(round_def, record)
    record["verdict"] = driver.judge_round(round_def, record)
    assert record["verdict"]["evaluation"] == "not_evaluated_no_oracle"
    assert record["verdict"]["passed"] is False


def test_tool_loop_discovery_failure_keeps_round_runtime_incomplete(driver) -> None:
    class _BrokenDiscoverySession(_FakeMcpSession):
        async def call(self, name, arguments):
            raise RuntimeError(f"MCP transport failed for {name}")

    round_def = {
        "question_id": "CQ-LOOP-08",
        "principal_env": "R3006_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "未授权的问题",
        "expected_rows": None,
        "expected_columns": None,
        "expected_answer_points": [],
        "protected": {"require_no_sql": True, "require_unconfirmable": True},
        "expected_rows_order_matters": False,
    }
    record = _run_round(
        driver,
        round_def,
        [{"content": "无法确认"}],
        _FakeAdapter({}),
        max_turns=3,
        session_factory=lambda key: _BrokenDiscoverySession("runtime-scope-digest"),
    )

    # an MCP outage is not proof of correct authorization behavior: even though
    # the model answered 无法确认, the round stays runtime-incomplete
    assert record["runtime_context_status"] == "error"
    assert record["runtime_completion"]["semantic_discovery"] == "error"
    assert record["runtime_completion"]["reason"] == "semantic_discovery_failed"
    assert record["runtime_completion"]["completed"] is False
    assert record["protection"]["verdict"] == "pass"
    assert record["verdict"]["passed"] is False


# --------------------------- T-G6-4: frozen adapter subprocess error contract


def _env_without_dsn() -> dict[str, str]:
    env = dict(os.environ)
    env.pop(DSN_ENV, None)
    return env


def test_execute_sql_invokes_frozen_adapter_and_preserves_missing_dsn_contract(
    driver, monkeypatch
) -> None:
    captured: dict = {}

    real_run = subprocess.run

    def spy_run(argv, **kwargs):
        captured["argv"] = argv
        return real_run(argv, **kwargs)

    monkeypatch.setattr(driver.subprocess, "run", spy_run)
    payload = driver.run_execute_sql("SELECT 1", env=_env_without_dsn())

    assert captured["argv"][1] == str(ADAPTER_PATH)
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "config_error"
    assert DSN_ENV in payload["error"]["message"]
    assert payload["adapter_exit_code"] == 1


def test_execute_sql_passes_sql_through_and_keeps_input_error_contract(driver) -> None:
    payload = driver.run_execute_sql("SELECT 1; SELECT 2", env=_env_without_dsn())
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "input_error"

    payload = driver.run_execute_sql("   ", env=_env_without_dsn())
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "input_error"


def test_execute_sql_reports_adapter_process_failure_narrowly(driver, tmp_path) -> None:
    payload = driver.run_execute_sql(
        "SELECT 1", adapter=tmp_path / "does-not-exist.py", env=_env_without_dsn()
    )
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "driver_error"


# ------------------------- T-G6-1: CLI help and truthful configuration status


def _cli_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        DSN_ENV,
        "R3006_SMOKE_KEY_GRANT",
        "R3006_SMOKE_KEY_NOGRANT",
        "R3006_SMOKE_LLM_BASE_URL",
        "R3006_SMOKE_LLM_API_KEY",
        "R3006_SMOKE_LLM_MODEL",
    ):
        env.pop(name, None)
    return env


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DRIVER_PATH), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_cli_help_is_usable_before_authorization() -> None:
    proc = _run_cli(["--help"], _cli_env())
    assert proc.returncode == 0
    for token in ("--check", "--rounds", "--evidence-dir", DSN_ENV):
        assert token in proc.stdout


def test_cli_check_reports_missing_configuration_without_execution(tmp_path) -> None:
    rounds_path = _write_rounds(tmp_path, [_isolation_round()])
    proc = _run_cli(["--check", "--rounds", str(rounds_path)], _cli_env())

    assert proc.returncode != 0
    assert "readiness: NOT READY" in proc.stdout
    # every missing item is listed truthfully
    for name in (
        "rounds_file: ok",
        "R3006_SMOKE_KEY_GRANT: missing",
        f"{DSN_ENV}: missing",
        "R3006_SMOKE_LLM_BASE_URL: missing",
        "R3006_SMOKE_LLM_API_KEY: missing",
        "R3006_SMOKE_LLM_MODEL: missing",
    ):
        assert name in proc.stdout
    assert "未执行" in proc.stdout
    # no real or simulated SQL acceptance may be claimed here
    assert "readiness: READY" not in proc.stdout


def test_cli_run_mode_requires_rounds_and_rejects_invalid_file(tmp_path) -> None:
    missing = _run_cli([], _cli_env())
    assert missing.returncode == 2
    assert "--rounds" in missing.stderr

    bad = _write_rounds(tmp_path, [dict(_isolation_round(), unexpected="x")])
    blocked = _run_cli(["--rounds", str(bad), "--evidence-dir", str(tmp_path / "ev")], _cli_env())
    assert blocked.returncode == 2
    assert "BLOCKED" in blocked.stderr

    no_env = _write_rounds(tmp_path, [_isolation_round()])
    blocked_env = _run_cli(
        ["--rounds", str(no_env), "--evidence-dir", str(tmp_path / "ev2")], _cli_env()
    )
    assert blocked_env.returncode == 2
    assert "missing required environment variables" in blocked_env.stderr
