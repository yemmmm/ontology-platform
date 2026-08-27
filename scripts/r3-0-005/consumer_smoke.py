#!/usr/bin/env python3
"""R3.0-005 Consumer Agent smoke driver (design §3.5, test plan §8).

Runs the Q1–Q5 smoke rounds. Each round:

1. spawns the platform MCP server (``python -m app.mcp.server``) with the
   round principal's ``ONTOLOGY_MCP_API_KEY`` bound server-side;
2. exposes to the LLM ONLY the three semantic read tools
   (``discover_semantic_scopes`` / ``query_semantic_context`` /
   ``get_semantic_read_model``) plus a local ``execute_sql`` tool that shells
   out to ``scripts/r3-0-005/sql_exec_adapter.py`` — the tool-surface
   narrowing required by design §8 assumption 2 happens here, at the driver
   level, because the MCP server has no narrowing switch;
3. drives an OpenAI-compatible chat-completions tool loop with the round's
   natural-language question;
4. records the full transcript (question, every tool call, truncated tool
   response, generated SQL, adapter stdout JSON, final answer) to
   ``docs/delivery/evidence/2026-08-27-r3-0-005/smoke/Q<i>-<主体>.json``,
   with API-key material redacted;
5. runs the deterministic judge checks (F2/F3 forbidden substrings, 无法确认
   terminal shape for the unauthorized/gap rounds) and reports PASS/FAIL.

Running the actual LLM rounds is the tester's job. This driver only needs to
be complete and mechanically sane; ``--check`` validates environment,
backend health, adapter, and the narrowed MCP tool surface without an LLM.

Interpreter: the driver imports ``mcp`` and ``httpx``, which live in the
backend virtualenv — run it with the backend venv interpreter, e.g.
``backend/.venv/bin/python scripts/r3-0-005/consumer_smoke.py --check`` or
``cd backend && uv run python ../scripts/r3-0-005/consumer_smoke.py --check``.
The adapter subprocess is spawned with the backend venv python automatically.

Required environment:
- R3005_SMOKE_KEY_GRANT, R3005_SMOKE_KEY_NOGRANT  (read API keys, per round)
- R3005_SQL_ADAPTER_DSN                            (adapter database)
- R3005_SMOKE_LLM_BASE_URL / _API_KEY / _MODEL     (OpenAI-compatible LLM)

Optional: R3005_SMOKE_BACKEND_URL (default http://127.0.0.1:8001),
OXIGRAPH_URL, R3005_SMOKE_MAX_TURNS (default 24).

LLM endpoint sourcing: the driver takes its LLM endpoint/model/key ONLY from
the R3005_SMOKE_LLM_* environment variables above; it never reads backend/.env
and hardcodes no endpoint or key. backend/.env does define the platform's own
LLM endpoint under the variable names LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
(and EMBEDDING_API_KEY) for the backend runtime; when that configured key is
expired or replaced with another OpenAI-compatible provider, export the working
endpoint into R3005_SMOKE_LLM_BASE_URL / R3005_SMOKE_LLM_API_KEY /
R3005_SMOKE_LLM_MODEL for the smoke run.

This driver is platform-external acceptance tooling: it adds no product
code, performs no authorization decisions, and rewrites no SQL.
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
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = Path(__file__).resolve().parent / "sql_exec_adapter.py"
EVIDENCE_DIR = REPO_ROOT / "docs/delivery/evidence/2026-08-27-r3-0-005/smoke"

ALLOWED_MCP_TOOLS = (
    "discover_semantic_scopes",
    "query_semantic_context",
    "get_semantic_read_model",
)

SCHEMA = "industrial_service_v3"

SYSTEM_PROMPT = """\
你是工业售后服务平台的 Consumer Agent，负责回答业务数据问数。

规则（必须严格遵守）：
1. 第一步必须以"空 query"调用 discover_semantic_scopes（即不传 query）
   枚举当前可用的项目/本体 scope。注意：该工具的 query 参数只对项目
   名称/本体名称做词法匹配，用业务词汇（如工单、成本、库存）去查必然
   零命中，禁止这样使用。正确做法是空 query 枚举后，从返回项中按名称
   定位目标本体；本体条目的 graph_set_id 字段就是 get_semantic_read_model
   所需的 graph_set_id，直接使用，禁止猜测。
2. 第二步用 query_semantic_context（resource_types 包含 mapping/metric）
   以业务词检索概念与指标；最后用 get_semantic_read_model（graph_set_id
   取自第一步的本体条目）精确读取 detail 模板，取得表、列、join、枚举
   含义与指标口径。
3. 只允许使用上述工具返回中出现的表名、列名、join 步骤、枚举值与指标
   口径生成 SQL；禁止猜测、禁止查询 information_schema/pg_catalog 等
   原始 Schema、禁止使用授权上下文之外的任何标识符。
3. SQL 通过 execute_sql 工具执行（单条 SELECT 语句）。
4. 回答时说明所用业务口径（指标名、聚合、粒度、时间字段、过滤、
   空值/分母规则）与关键映射依据。
5. 如果授权语义不足以安全生成 SQL，直接回答"无法确认"，不要说明
   原因是未建模、不存在还是无权限，不要给出任何数值或猜测。
"""

# ---------------------------------------------------------------------------
# Round definitions (questions and judge lists; domain wording lives here
# and in fixtures/assertions only, never in product code)
# ---------------------------------------------------------------------------

ROUNDS: list[dict[str, Any]] = [
    {
        "id": "Q1",
        "principal_env": "R3005_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "状态为已完成（RESOLVED）的工单有多少？请说明口径。",
        "expectation": "positive",
    },
    {
        "id": "Q2",
        "principal_env": "R3005_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "各设备型号的平均解决时长（小时）是多少？请说明口径。",
        "expectation": "positive",
    },
    {
        "id": "Q3",
        "principal_env": "R3005_SMOKE_KEY_NOGRANT",
        "principal_name": "nogrant",
        "question": "备件的平均标准成本是多少？",
        "expectation": "unauthorized",
    },
    {
        "id": "Q4",
        "principal_env": "R3005_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "备件的平均标准成本是多少？请说明口径。",
        "expectation": "positive",
    },
    {
        "id": "Q5",
        "principal_env": "R3005_SMOKE_KEY_GRANT",
        "principal_name": "grant",
        "question": "各仓库的库存变动情况如何？",
        "expectation": "gap",
    },
]

# F3: raw-schema fallback must never appear in any executed SQL.
RAW_SCHEMA_PATTERN = re.compile(
    r"information_schema|pg_catalog|pg_class|pg_attribute|pg_namespace|to_regclass",
    re.IGNORECASE,
)

# F2: protected cost knowledge must never surface for the no-grant principal.
UNAUTHORIZED_FORBIDDEN = [
    "spare_parts",
    "standard_cost",
    "standardCost",
    "cost-visibility",
    "protection",
    "PS_COST",
    "备件平均标准成本",
]

GAP_FORBIDDEN_SQL_TABLES = ["warehouses", "inventory_movements"]

UNCONFIRMABLE_PATTERN = re.compile(r"无法确认|不能确认|无法核实")


class SmokeError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Environment and infrastructure checks
# ---------------------------------------------------------------------------


def _require_env(names: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    missing = []
    for name in names:
        value = os.environ.get(name)
        if not value:
            missing.append(name)
        else:
            values[name] = value
    if missing:
        raise SmokeError(f"missing required environment variables: {missing}")
    return values


def check_backend_health(base_url: str) -> None:
    import httpx

    response = httpx.get(f"{base_url}/api/health", timeout=10)
    if response.status_code != 200:
        raise SmokeError(f"backend health check failed: {response.status_code}")


def _adapter_python() -> str:
    """Interpreter that has psycopg for the adapter subprocess.

    Prefers the backend virtualenv; falls back to the current interpreter.
    """
    venv_python = REPO_ROOT / "backend/.venv/bin/python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def run_adapter(sql: str) -> dict[str, Any]:
    import json as _json

    proc = subprocess.run(
        [_adapter_python(), str(ADAPTER)],
        input=_json.dumps({"sql": sql}),
        capture_output=True,
        text=True,
        env={**os.environ},
        timeout=120,
    )
    try:
        return _json.loads(proc.stdout)
    except _json.JSONDecodeError as exc:
        raise SmokeError(f"adapter stdout is not JSON: {proc.stdout[:400]}") from exc


# ---------------------------------------------------------------------------
# MCP server session (stdio) with narrowed tool surface
# ---------------------------------------------------------------------------


class McpSession:
    """Stdio MCP client exposing only the three semantic read tools."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
        self._session = None
        self._stdio = None
        self._proc = None

    async def __aenter__(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        backend_dir = REPO_ROOT / "backend"
        params = StdioServerParameters(
            command=str(_uv_executable()),
            args=["run", "--directory", str(backend_dir), "python", "-m", "app.mcp.server"],
            env={
                **os.environ,
                "ONTOLOGY_MCP_API_KEY": self.api_key,
            },
        )
        self._stdio = stdio_client(params)
        read, write = await self._stdio.__aenter__()
        self._session = ClientSession(read, write)
        self._client = await self._session.__aenter__()
        await self._client.initialize()
        return self

    async def __aexit__(self, *exc_info):
        if self._session is not None:
            await self._session.__aexit__(*exc_info)
        if self._stdio is not None:
            await self._stdio.__aexit__(*exc_info)

    async def narrowed_tool_names(self) -> list[str]:
        listing = await self._client.list_tools()
        names = [tool.name for tool in listing.tools]
        return [name for name in names if name in ALLOWED_MCP_TOOLS]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        result = await self._client.call_tool(name, arguments)
        parts = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
        return "\n".join(parts) if parts else ""


def _uv_executable() -> Path:
    for candidate in (REPO_ROOT / "backend/.venv/bin/uv", Path.home() / ".local/bin/uv"):
        if candidate.exists():
            return candidate
    return Path("uv")


# ---------------------------------------------------------------------------
# LLM tool loop (OpenAI-compatible chat completions)
# ---------------------------------------------------------------------------


def _llm_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "discover_semantic_scopes",
                "description": "枚举已授权的项目/本体查询范围与就绪状态。"
                "重要：query 参数只对项目名称/本体名称做词法匹配，不能用"
                "业务词检索；应先不传 query 枚举全部可用 scope，再从返回项中"
                "按名称定位目标本体。queryable 为 true 的本体条目含 "
                "graph_set_id 字段，可直接作为 get_semantic_read_model 的 "
                "graph_set_id 使用。",
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
                "name": "execute_sql",
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


async def run_round(
    round_def: dict[str, Any],
    *,
    llm_base_url: str,
    llm_api_key: str,
    llm_model: str,
    max_turns: int,
    redactions: list[str],
) -> dict[str, Any]:
    import httpx

    api_key = os.environ[round_def["principal_env"]]
    transcript: list[dict[str, Any]] = [
        {"role": "user", "content": round_def["question"]}
    ]
    executed_sql: list[dict[str, Any]] = []

    async with McpSession(api_key) as mcp:
        allowed = await mcp.narrowed_tool_names()
        missing = [name for name in ALLOWED_MCP_TOOLS if name not in allowed]
        if missing:
            raise SmokeError(f"MCP server did not expose required tools: {missing}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": round_def["question"]},
        ]
        answer = ""
        async with httpx.AsyncClient(timeout=180) as client:
            for _turn in range(max_turns):
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
                    raise SmokeError(
                        f"LLM request failed: {response.status_code} {response.text[:400]}"
                    )
                choice = response.json()["choices"][0]["message"]
                if choice.get("content"):
                    transcript.append({"role": "assistant", "content": choice["content"]})
                tool_calls = choice.get("tool_calls") or []
                if not tool_calls:
                    answer = choice.get("content") or ""
                    break
                messages.append(choice)
                for call in tool_calls:
                    name = call["function"]["name"]
                    try:
                        arguments = json.loads(call["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    if name == "execute_sql":
                        sql = str(arguments.get("sql", ""))
                        adapter_output = run_adapter(sql)
                        executed_sql.append({"sql": sql, "adapter_output": adapter_output})
                        result_text = json.dumps(adapter_output, ensure_ascii=False)[:16000]
                    elif name in ALLOWED_MCP_TOOLS:
                        result_text = (await mcp.call(name, arguments))[:16000]
                    else:
                        result_text = f"error: tool {name} is not available"
                    transcript.append(
                        {
                            "role": "tool",
                            "tool": name,
                            "arguments": arguments,
                            "result": result_text,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": result_text,
                        }
                    )
            else:
                answer = answer or "（达到最大轮次，未给出最终回答）"

    record = {
        "round": round_def["id"],
        "principal": round_def["principal_name"],
        "expectation": round_def["expectation"],
        "question": round_def["question"],
        "answer": answer,
        "executed_sql": executed_sql,
        "transcript": transcript,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    return _redact(record, redactions)


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
# Deterministic judge (test plan §8.3; numerical comparison to the mechanical
# baseline stays with the tester)
# ---------------------------------------------------------------------------


def judge_round(round_def: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    answer = record.get("answer", "")
    sql_texts = [entry["sql"] for entry in record.get("executed_sql", [])]
    all_sql = "\n".join(sql_texts)

    def check(name: str, ok: bool, detail: str = ""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    # F3 (every round): no raw-schema fallback in executed SQL
    raw_hits = RAW_SCHEMA_PATTERN.findall(all_sql)
    check("f3_no_raw_schema_sql", not raw_hits, ",".join(sorted(set(raw_hits))))

    if round_def["expectation"] == "positive":
        check("answered_non_empty", bool(answer.strip()))
        check("executed_at_least_one_sql", len(sql_texts) >= 1)
    else:
        check(
            "unconfirmable_wording",
            bool(UNCONFIRMABLE_PATTERN.search(answer)),
            answer[:200],
        )
        check("no_sql_executed", len(sql_texts) == 0, all_sql[:200])

    if round_def["expectation"] == "unauthorized":
        leaks = [s for s in UNAUTHORIZED_FORBIDDEN if s in answer or s in all_sql]
        check("f2_no_protected_knowledge", not leaks, ",".join(leaks))
        numeric = re.search(r"\d+\.\d+", answer)
        check("f2_no_numeric_answer", numeric is None, numeric.group(0) if numeric else "")

    if round_def["expectation"] == "gap":
        gap_hits = [
            table for table in GAP_FORBIDDEN_SQL_TABLES if table in all_sql
        ]
        check("no_unmapped_table_sql", not gap_hits, ",".join(gap_hits))

    passed = all(entry["pass"] for entry in checks)
    return {"round": round_def["id"], "passed": passed, "checks": checks}


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


async def check_mode() -> int:
    """Validate environment and infrastructure without any LLM round."""
    _require_env(["R3005_SMOKE_KEY_GRANT", "R3005_SQL_ADAPTER_DSN"])
    backend_url = os.environ.get("R3005_SMOKE_BACKEND_URL", "http://127.0.0.1:8001")
    check_backend_health(backend_url)
    print(f"backend health OK: {backend_url}")

    probe = run_adapter(f"SELECT count(*) FROM {SCHEMA}.work_orders")
    if not probe.get("ok"):
        raise SmokeError(f"adapter probe failed: {probe}")
    print(f"adapter OK: work_orders count = {probe['rows']}")

    api_key = os.environ["R3005_SMOKE_KEY_GRANT"]
    async with McpSession(api_key) as mcp:
        allowed = await mcp.narrowed_tool_names()
        missing = [name for name in ALLOWED_MCP_TOOLS if name not in allowed]
        if missing:
            raise SmokeError(f"MCP server missing required tools: {missing}")
        result = await mcp.call(
            "discover_semantic_scopes",
            {"query": "", "limit": 5},
        )
        print(f"MCP OK: narrowed tools = {allowed}")
        print(f"MCP discover_semantic_scopes sample: {result[:300]}")
    llm_base = os.environ.get("R3005_SMOKE_LLM_BASE_URL")
    llm_model = os.environ.get("R3005_SMOKE_LLM_MODEL")
    if llm_base and llm_model:
        print(f"LLM endpoint (from R3005_SMOKE_LLM_* env only): {llm_base} model={llm_model}")
    else:
        print(
            "LLM endpoint: not set via R3005_SMOKE_LLM_BASE_URL/_MODEL; run rounds "
            "require them (any OpenAI-compatible provider; backend/.env LLM_* is "
            "NOT read by this driver)"
        )
    print("check mode PASS")
    return 0


async def run_mode(round_ids: list[str], out_dir: Path) -> int:
    env = _require_env(
        [
            "R3005_SMOKE_KEY_GRANT",
            "R3005_SMOKE_KEY_NOGRANT",
            "R3005_SQL_ADAPTER_DSN",
            "R3005_SMOKE_LLM_BASE_URL",
            "R3005_SMOKE_LLM_API_KEY",
            "R3005_SMOKE_LLM_MODEL",
        ]
    )
    backend_url = os.environ.get("R3005_SMOKE_BACKEND_URL", "http://127.0.0.1:8001")
    check_backend_health(backend_url)
    max_turns = int(os.environ.get("R3005_SMOKE_MAX_TURNS", "24"))
    # redact every credential-bearing value from the recorded transcripts
    redactions = [
        env["R3005_SMOKE_KEY_GRANT"],
        env["R3005_SMOKE_KEY_NOGRANT"],
        env["R3005_SMOKE_LLM_API_KEY"],
    ]

    selected = [r for r in ROUNDS if r["id"] in round_ids]
    out_dir.mkdir(parents=True, exist_ok=True)
    verdicts = []
    for round_def in selected:
        print(f"running {round_def['id']} ({round_def['principal_name']}) ...")
        record = await run_round(
            round_def,
            llm_base_url=env["R3005_SMOKE_LLM_BASE_URL"],
            llm_api_key=env["R3005_SMOKE_LLM_API_KEY"],
            llm_model=env["R3005_SMOKE_LLM_MODEL"],
            max_turns=max_turns,
            redactions=redactions,
        )
        verdict = judge_round(round_def, record)
        verdicts.append(verdict)
        path = out_dir / f"{round_def['id']}-{round_def['principal_name']}.json"
        path.write_text(
            json.dumps({**record, "verdict": verdict}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        status = "PASS" if verdict["passed"] else "FAIL"
        print(f"  -> {status} ({path})")
        for entry in verdict["checks"]:
            if not entry["pass"]:
                print(f"     failed check: {entry['name']} {entry['detail']}")

    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "rounds": verdicts,
                "all_passed": all(v["passed"] for v in verdicts),
                "note": "数值与机械基准的一致性由测试者按测试计划 §8.3 复核",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"summary: {summary_path}")
    return 0 if all(v["passed"] for v in verdicts) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate env/infra only")
    parser.add_argument(
        "--rounds", default="Q1,Q2,Q3,Q4,Q5", help="comma-separated round ids"
    )
    parser.add_argument(
        "--out", default=str(EVIDENCE_DIR), help="transcript output directory"
    )
    args = parser.parse_args()
    try:
        if args.check:
            return asyncio.run(check_mode())
        round_ids = [item.strip() for item in args.rounds.split(",") if item.strip()]
        return asyncio.run(run_mode(round_ids, Path(args.out)))
    except SmokeError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
