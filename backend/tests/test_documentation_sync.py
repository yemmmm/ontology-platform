from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync-interface-docs.py"
API_DOC = ROOT / "docs" / "api.md"
MCP_DOC = ROOT / "docs" / "mcp.md"


def _module():
    spec = importlib.util.spec_from_file_location("sync_interface_docs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generated_blocks_match_runtime_exactly() -> None:
    module = _module()
    api = API_DOC.read_text(encoding="utf-8")
    mcp = MCP_DOC.read_text(encoding="utf-8")
    assert module.render_http_inventory() in api
    assert module.render_mcp_inventory() in mcp

    http_rows = module.enumerate_http_operations()
    tools = module.enumerate_mcp_tools()
    assert len(http_rows) == len({(row["method"], row["path"]) for row in http_rows})
    assert len(tools) == len({tool["name"] for tool in tools})


def test_default_check_is_read_only_and_cwd_independent(tmp_path: Path) -> None:
    before = {_hash(API_DOC), _hash(MCP_DOC)}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert {_hash(API_DOC), _hash(MCP_DOC)} == before


def test_write_is_idempotent() -> None:
    before = (API_DOC.read_bytes(), MCP_DOC.read_bytes())
    subprocess.run([sys.executable, str(SCRIPT), "--write"], cwd=ROOT, check=True)
    after_first = (API_DOC.read_bytes(), MCP_DOC.read_bytes())
    subprocess.run([sys.executable, str(SCRIPT), "--write"], cwd=ROOT / "backend", check=True)
    after_second = (API_DOC.read_bytes(), MCP_DOC.read_bytes())
    assert before == after_first == after_second


def test_replacement_fails_closed_for_invalid_markers() -> None:
    module = _module()
    for text in ("no markers", "BEGIN END BEGIN", "END then BEGIN"):
        try:
            module.replace_generated_block(text, "BEGIN", "END", "replacement")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid markers accepted: {text}")


def test_rendering_detects_runtime_drift(monkeypatch) -> None:
    module = _module()
    existing = module.render_http_inventory()
    original = module.enumerate_http_operations

    def changed():
        return [
            *original(),
            {"tag": "test", "method": "GET", "path": "/api/test-drift", "summary": "A | B"},
        ]

    monkeypatch.setattr(module, "enumerate_http_operations", changed)
    assert module.render_http_inventory() != existing
    assert "A \\| B" in module.render_http_inventory()


def test_check_detects_and_write_repairs_http_and_mcp_drift(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    module = _module()
    api_doc = tmp_path / "api.md"
    mcp_doc = tmp_path / "mcp.md"
    api_doc.write_text(API_DOC.read_text(encoding="utf-8"), encoding="utf-8")
    mcp_doc.write_text(MCP_DOC.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "API_DOC", api_doc)
    monkeypatch.setattr(module, "MCP_DOC", mcp_doc)

    original_http = module.enumerate_http_operations
    original_mcp = module.enumerate_mcp_tools
    monkeypatch.setattr(
        module,
        "enumerate_http_operations",
        lambda: [
            *original_http(),
            {"tag": "test", "method": "GET", "path": "/api/test-drift", "summary": "drift"},
        ],
    )
    monkeypatch.setattr(
        module,
        "enumerate_mcp_tools",
        lambda: [
            *original_mcp(),
            {
                "category": "test",
                "name": "test_drift_tool",
                "description": "drift",
                "input_schema_summary": {"required": [], "properties": []},
                "source_file": "test.py",
            },
        ],
    )

    assert module.check_documents() == 1
    assert "api.md" in capsys.readouterr().err
    assert module.write_documents() == 0
    assert module.check_documents() == 0
    assert "test_drift_tool" in mcp_doc.read_text(encoding="utf-8")


def test_explicit_http_references_exist_in_openapi() -> None:
    module = _module()
    operations = {(item["method"], item["path"]) for item in module.enumerate_http_operations()}
    pattern = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE) (/api/[^\s`),]+)")
    for path in (ROOT / "README.md", API_DOC, ROOT / "docs" / "platform-guide.md"):
        for method, raw_path in pattern.findall(path.read_text(encoding="utf-8")):
            public_path = raw_path.split("?", 1)[0].rstrip(".；。")
            assert (method, public_path) in operations, (
                f"stale reference in {path}: {method} {public_path}"
            )


def test_configuration_and_requirement_statuses_are_truthful() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    requirements = (ROOT / "docs" / "requirements-v1.0.md").read_text(encoding="utf-8")
    assert "ONTOLOGY_MCP_API_KEY" in readme
    assert "backend/.local/ontology-platform-bootstrap.json" in readme
    assert "ONTOLOGY_UI_ORIGINS" in env
    assert "SECRET_KEY" in env
    assert "localhost:5434" in env
    assert "8001" in readme and "5173" in readme and "7878" in readme
    for requirement_id, status in (
        ("R-008", "已实现"),
        ("R-009", "挂起（Pending）"),
        ("R-010", "已调整"),
    ):
        row = re.search(rf"^\| {requirement_id} \|.*$", requirements, re.MULTILINE)
        assert row and f"| {status} |" in row.group(0)
        detail = re.search(
            rf"^### {requirement_id} [^\n]+\n\n当前状态：`([^`]+)`$",
            requirements,
            re.MULTILINE,
        )
        assert detail and detail.group(1) == status


def test_start_local_initializes_custom_postgres_port_without_docker(tmp_path: Path) -> None:
    temporary_repo = tmp_path / "repo"
    scripts_dir = temporary_repo / "scripts"
    backend_dir = temporary_repo / "backend"
    scripts_dir.mkdir(parents=True)
    backend_dir.mkdir()
    shutil.copy2(ROOT / "scripts" / "start-local.sh", scripts_dir / "start-local.sh")
    shutil.copy2(ROOT / ".env.example", temporary_repo / ".env.example")

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" && ensure_backend_env',
            "bash",
            str(scripts_dir / "start-local.sh"),
        ],
        env={**os.environ, "POSTGRES_PORT": "5544"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    generated = (backend_dir / ".env").read_text(encoding="utf-8")
    assert re.search(r"^POSTGRES_PORT=5544$", generated, re.MULTILINE)
    assert re.search(r"^DATABASE_URL=.*@localhost:5544/", generated, re.MULTILINE)
    assert "localhost:5434/" not in generated


def test_ontology_builder_dependency_contract_uses_registry() -> None:
    cases = json.loads(
        (ROOT / "skills" / "ontology-builder" / "evals" / "cases.json").read_text(encoding="utf-8")
    )
    required = {tool for case in cases for tool in case["assertions"].get("required_tools", [])}
    registry = {tool["name"] for tool in _module().enumerate_mcp_tools()}
    assert required <= registry
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "skills" / "ontology-builder").rglob("*.md")
    )
    for stale in (
        "get_evidence_artifact_status",
        "get_evidence_artifact_chunks",
        "validate_proposal",
        "create_data_source",
        "create_semantic_mapping",
        "run_connector_query",
    ):
        assert stale not in combined
