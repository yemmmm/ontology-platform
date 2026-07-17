"""Opt-in v1 release acceptance against the running PostgreSQL/Oxigraph service.

Run with ``RUN_V1_FULL_CHAIN_ACCEPTANCE=1 uv run pytest
tests/test_v1_full_chain_acceptance.py``.  This is intentionally a real HTTP
and stdio-MCP harness, not a TestClient fixture: it changes the user systemd
manager environment to exercise R-004's ``rdf_primary`` path and restores it
on every exit path.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.repositories.models import (
    ModelingBatchModel,
    ModelingBatchAttemptModel,
    SecurityAuditEventModel,
    SemanticEditAuditModel,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_V1_FULL_CHAIN_ACCEPTANCE") != "1",
    reason="set RUN_V1_FULL_CHAIN_ACCEPTANCE=1 to run against the local service",
)

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
BOOTSTRAP = BACKEND / ".local" / "ontology-platform-bootstrap.json"
API_URL = os.getenv("V1_ACCEPTANCE_API_URL", "http://127.0.0.1:8001/api")


def _manager_mode() -> str | None:
    output = subprocess.check_output(
        ["systemctl", "--user", "show-environment"], text=True, cwd=ROOT
    )
    prefix = "SEMANTIC_PRODUCT_WRITE_MODE="
    return next(
        (line.removeprefix(prefix) for line in output.splitlines() if line.startswith(prefix)), None
    )


def _restart_and_assert_mode(client: httpx.Client, value: str | None) -> None:
    command = ["systemctl", "--user"]
    if value is None:
        subprocess.run([*command, "unset-environment", "SEMANTIC_PRODUCT_WRITE_MODE"], check=True)
    else:
        subprocess.run(
            [*command, "set-environment", f"SEMANTIC_PRODUCT_WRITE_MODE={value}"], check=True
        )
    subprocess.run([*command, "restart", "ontology-platform.service"], check=True)
    subprocess.run([*command, "is-active", "--quiet", "ontology-platform.service"], check=True)
    for _attempt in range(60):
        try:
            if client.get("/health").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        pytest.fail("ontology-platform.service did not expose /api/health within 60 seconds")
    mode = client.get("/semantic/canonical-mode")
    assert mode.status_code == 200, mode.text
    assert mode.json()["product_write_mode"] == (value or "legacy_only")


@pytest.fixture(scope="module")
def live() -> Iterator[tuple[httpx.Client, str]]:
    """Yield an authenticated real HTTP client and always restore manager state."""
    if not BOOTSTRAP.exists():
        pytest.fail(f"bootstrap credentials are required at {BOOTSTRAP}")
    bootstrap = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
    api_key = bootstrap.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        pytest.fail("bootstrap credential file has no API key")
    original_mode = _manager_mode()
    client = httpx.Client(
        base_url=API_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=30
    )
    try:
        _restart_and_assert_mode(client, "rdf_primary")
        yield client, api_key
    finally:
        try:
            _restart_and_assert_mode(client, original_mode)
        finally:
            client.close()


def _request(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    response = client.request(method, path, **kwargs)
    assert response.status_code < 400, f"{method} {path}: {response.status_code} {response.text}"
    return response.json() if response.content else {}


def _operation(suffix: str) -> dict:
    return {
        "operation_id": f"publish-{suffix}",
        "name": f"Publish {suffix}",
        "aliases": [],
        "description": "Publish a modeled customer.",
        "target_resource_type_iri": {
            "item_ref": {"client_item_id": "customer", "output": "resource_iri"}
        },
        "parameters": [],
        "preconditions": [],
        "effects": [],
        "possible_failures": [],
        "idempotency": {"kind": "idempotent"},
        "risk_level": "low",
        "tool_bindings": [
            {
                "binding_id": "publish",
                "kind": "mcp_tool",
                "system": "generic",
                "operation_identifier": "publish_customer",
            }
        ],
        "credential_requirements": [],
        "status": "active",
        "schema_version": "operation-v1",
    }


async def _mcp_probe(
    key: str, project_id: str, foreign_project_id: str, ontology_id: str, resource_iri: str
) -> None:
    def envelope(result) -> dict:
        assert result.content and hasattr(result.content[0], "text")
        return json.loads(result.content[0].text)

    parameters = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "app.mcp.server"],
        cwd=str(BACKEND),
        env={**os.environ, "ONTOLOGY_MCP_API_KEY": key},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            assert len((await session.list_tools()).tools) >= 1
            owned = await session.call_tool("get_project_build_context", {"project_id": project_id})
            assert not owned.isError and envelope(owned)["ok"] is True
            foreign = await session.call_tool(
                "get_project_build_context", {"project_id": foreign_project_id}
            )
            assert not foreign.isError and envelope(foreign)["ok"] is False
            lineage = await session.call_tool(
                "get_ontology_lineage",
                {"ontology_id": ontology_id, "target_type": "resource", "target_id": resource_iri},
            )
            assert not lineage.isError and envelope(lineage)["ok"] is True


def test_v1_full_chain_http_mcp_recovery_and_isolation(live: tuple[httpx.Client, str]) -> None:
    """R-001..R-008/R-011 release chain, including cleanup of its owned data."""
    client, _admin_key = live
    suffix = f"v1accept-{uuid4().hex[:12]}"
    created_projects: list[str] = []
    temporary_key_id: str | None = None
    try:
        p1 = _request(client, "POST", "/projects", json={"name": f"P1 {suffix}"})
        p2 = _request(client, "POST", "/projects", json={"name": f"P2 {suffix}"})
        created_projects.extend([p1["id"], p2["id"]])
        o1 = _request(
            client, "POST", f"/projects/{p1['id']}/ontologies", json={"name": f"O1 {suffix}"}
        )
        o2 = _request(
            client, "POST", f"/projects/{p1['id']}/ontologies", json={"name": f"O2 {suffix}"}
        )
        foreign = _request(
            client, "POST", f"/projects/{p2['id']}/ontologies", json={"name": f"O3 {suffix}"}
        )
        assert o1["workspace"]["state"] == "ready"
        assert {member["role"] for member in o1["workspace"]["members"]} >= {
            "asserted_ontology",
            "asserted_data",
            "shapes",
            "policy",
        }

        build = _request(
            client,
            "POST",
            f"/projects/{p1['id']}/build-sessions",
            json={"client_session_id": suffix},
        )
        checkpoint = _request(
            client,
            "POST",
            f"/build-sessions/{build['id']}/checkpoints",
            json={
                "client_checkpoint_id": f"start-{suffix}",
                "expected_revision": build["revision"],
                "phase": "modeling",
                "current_step": "acceptance",
                "next_step": "apply",
            },
        )
        lease = _request(
            client,
            "POST",
            f"/build-sessions/{build['id']}/ontology-leases/{o1['id']}:acquire",
            json={
                "client_request_id": f"lease-{suffix}",
                "expected_session_revision": checkpoint["session"]["revision"],
            },
        )
        context = _request(client, "GET", f"/ontologies/{o1['id']}/modeling-context")
        version = context["workspace"]["workspace_version"]
        items = [
            {
                "client_item_id": "customer",
                "command_kind": "create_class",
                "payload": {"name": f"Customer {suffix}"},
                "evidence": [
                    {"document_name": f"{suffix}.md", "excerpt": "A customer is modeled."}
                ],
            },
            {
                "client_item_id": "operation",
                "command_kind": "create_operation",
                "depends_on": ["customer"],
                "payload": _operation(suffix),
                "evidence": [
                    {"document_name": f"{suffix}.md", "excerpt": "Publishing is supported."}
                ],
            },
        ]
        dry = _request(
            client,
            "POST",
            f"/build-sessions/{build['id']}/modeling-batches",
            json={
                "client_batch_id": f"dry-{suffix}",
                "ontology_id": o1["id"],
                "idempotency_key": f"dry-{suffix}",
                "mode": "dry_run",
                "expected_workspace_version": version,
                "items": items,
            },
        )
        assert dry["attempt_status"] == "validated"
        applied_payload = {
            "client_batch_id": f"apply-{suffix}",
            "ontology_id": o1["id"],
            "idempotency_key": f"apply-{suffix}",
            "mode": "apply_atomic",
            "expected_workspace_version": version,
            "lease_token": lease["lease_token"],
            "actor": "forged-client-actor",
            "items": items,
        }
        applied = _request(
            client, "POST", f"/build-sessions/{build['id']}/modeling-batches", json=applied_payload
        )
        assert applied["attempt_status"] == "applied"
        replay = _request(
            client, "POST", f"/build-sessions/{build['id']}/modeling-batches", json=applied_payload
        )
        assert replay["attempt_id"] == applied["attempt_id"] and replay["created_attempt"] is False

        operation = next(item for item in applied["items"] if item["client_item_id"] == "operation")
        operation_iri = operation["resource_outputs"]["resource_iri"]
        references = _request(client, "GET", f"/projects/{p1['id']}/evidence-references")
        assert references["total"] == 2 and all(
            row["association_count"] == 1 for row in references["items"]
        )
        for reference in references["items"]:
            associations = _request(
                client, "GET", f"/evidence-references/{reference['id']}/associations"
            )
            assert associations["total"] == 1
        lineage = _request(
            client,
            "GET",
            f"/ontologies/{o1['id']}/lineage",
            params={"target_type": "resource", "target_id": operation_iri},
        )
        assert lineage["lineage_status"] in {"complete", "partial"}

        # R-004 failure fences: stale version and forbidden secret leave no new batch/operation output.
        stale = client.post(
            f"/build-sessions/{build['id']}/modeling-batches",
            json={
                **applied_payload,
                "client_batch_id": f"stale-{suffix}",
                "idempotency_key": f"stale-{suffix}",
            },
        )
        assert (
            stale.status_code == 409
            and stale.json()["detail"]["code"] == "workspace_revision_conflict"
        )
        secret = "v1-acceptance-secret-never-persisted"
        engine = create_engine(Settings().database_url)
        factory = sessionmaker(bind=engine)
        with factory() as db:
            batch_count = len(
                list(
                    db.scalars(
                        select(ModelingBatchModel).where(ModelingBatchModel.project_id == p1["id"])
                    )
                )
            )
        bad = client.post(
            f"/build-sessions/{build['id']}/modeling-batches",
            json={
                **applied_payload,
                "client_batch_id": f"secret-{suffix}",
                "idempotency_key": f"secret-{suffix}",
                "items": [
                    {
                        "client_item_id": "secret",
                        "command_kind": "create_class",
                        "payload": {"name": "Never persisted", "api_key": secret},
                    }
                ],
            },
        )
        assert bad.status_code == 422 and bad.json()["detail"]["code"] == "secret_in_payload"
        assert secret not in bad.text
        with factory() as db:
            assert (
                len(
                    list(
                        db.scalars(
                            select(ModelingBatchModel).where(
                                ModelingBatchModel.project_id == p1["id"]
                            )
                        )
                    )
                )
                == batch_count
            )
            assert secret not in repr(list(db.scalars(select(SecurityAuditEventModel.details))))
            attempt = db.get(ModelingBatchAttemptModel, applied["attempt_id"])
            assert attempt is not None
            audit = db.get(SemanticEditAuditModel, attempt.audit_id)
            assert audit is not None and audit.actor.startswith("key:")
        engine.dispose()

        # A spoofed payload field is logged as an override, but never becomes the persisted audit actor.
        spoofed = client.post(
            f"/build-sessions/{build['id']}/modeling-batches",
            json={
                **applied_payload,
                "client_batch_id": f"spoof-{suffix}",
                "idempotency_key": f"spoof-{suffix}",
                "actor": "forged",
            },
        )
        assert spoofed.status_code == 409
        engine = create_engine(Settings().database_url)
        factory = sessionmaker(bind=engine)
        with factory() as db:
            events = list(
                db.scalars(
                    select(SecurityAuditEventModel).where(
                        SecurityAuditEventModel.event_type == "actor_spoof_attempt"
                    )
                )
            )
            assert events and all("forged" not in repr(event.details) for event in events)
        engine.dispose()

        partial_context = _request(client, "GET", f"/ontologies/{o1['id']}/modeling-context")
        partial = _request(
            client,
            "POST",
            f"/build-sessions/{build['id']}/modeling-batches",
            json={
                "client_batch_id": f"partial-{suffix}",
                "ontology_id": o1["id"],
                "idempotency_key": f"partial-{suffix}",
                "mode": "apply_partial",
                "expected_workspace_version": partial_context["workspace"]["workspace_version"],
                "lease_token": lease["lease_token"],
                "items": [
                    {
                        "client_item_id": "good",
                        "command_kind": "create_class",
                        "payload": {"name": f"Partial {suffix}"},
                        "evidence": [
                            {"document_name": f"partial-{suffix}.md", "excerpt": "Good item."}
                        ],
                    },
                    {
                        "client_item_id": "bad",
                        "command_kind": "unknown_command",
                        "payload": {},
                        "evidence": [
                            {"document_name": f"partial-{suffix}.md", "excerpt": "Bad item."}
                        ],
                    },
                    {
                        "client_item_id": "blocked",
                        "command_kind": "create_class",
                        "depends_on": ["bad"],
                        "payload": {"name": "Blocked"},
                        "evidence": [
                            {"document_name": f"partial-{suffix}.md", "excerpt": "Blocked item."}
                        ],
                    },
                ],
            },
        )
        assert partial["attempt_status"] == "partially_applied"
        assert {row["client_item_id"]: row["status"] for row in partial["items"]} == {
            "good": "applied",
            "bad": "failed",
            "blocked": "blocked",
        }
        partial_refs = _request(client, "GET", f"/projects/{p1['id']}/evidence-references")
        partial_document_refs = [
            row for row in partial_refs["items"] if row["document_name"] == f"partial-{suffix}.md"
        ]
        assert (
            len(partial_document_refs) == 1 and partial_document_refs[0]["association_count"] == 1
        )
        partial_associations = _request(
            client,
            "GET",
            f"/evidence-references/{partial_document_refs[0]['id']}/associations",
        )
        assert partial_associations["total"] == 1
        partial_statuses = {row["client_item_id"]: row for row in partial["items"]}
        assert partial_associations["items"][0]["client_item_id"] == "good"
        good_iri = partial_statuses["good"]["resource_outputs"]["resource_iri"]
        partial_lineage = _request(
            client,
            "GET",
            f"/ontologies/{o1['id']}/lineage",
            params={"target_type": "resource", "target_id": good_iri},
        )
        assert partial_lineage["lineage_status"] in {"complete", "partial"}

        # Scope resolver must retain P1 ownership and must reject a mixed P2 scope.
        query = _request(
            client,
            "POST",
            "/semantic/context:query",
            json={
                "project_id": p1["id"],
                "scope_mode": "ontologies",
                "ontology_ids": [o1["id"], o2["id"]],
                "query": f"Customer {suffix}",
                "resource_types": ["concept", "operation"],
            },
        )
        assert {row["ontology_id"] for row in query["scope"]["ontologies"]} == {o1["id"], o2["id"]}
        mixed = client.post(
            "/semantic/context:query",
            json={
                "project_id": p1["id"],
                "scope_mode": "ontologies",
                "ontology_ids": [o1["id"], foreign["id"]],
                "query": "x",
            },
        )
        assert mixed.status_code in {403, 404}
        global_scope = _request(
            client,
            "POST",
            "/semantic/context:query",
            json={"project_id": p1["id"], "scope_mode": "project", "query": f"Customer {suffix}"},
        )
        assert {row["ontology_id"] for row in global_scope["scope"]["ontologies"]} == {
            o1["id"],
            o2["id"],
        }
        sparql = _request(
            client,
            "POST",
            "/semantic/sparql:query",
            json={
                "project_id": p1["id"],
                "scope_mode": "project",
                "query": "SELECT ?g WHERE { GRAPH ?g { ?s ?p ?o } }",
            },
        )
        foreign_graphs = {member["graph_iri"] for member in foreign["workspace"]["members"]}
        returned_graphs = {
            row["g"]["value"] for row in sparql["result"]["results"]["bindings"] if "g" in row
        }
        assert not returned_graphs & foreign_graphs

        temp = _request(
            client,
            "POST",
            "/api-keys",
            json={"name": f"accept-{suffix}", "project_id": p1["id"], "scopes": ["admin"]},
        )
        temporary_key_id = temp["id"]
        asyncio.run(_mcp_probe(temp["plaintext_key"], p1["id"], p2["id"], o1["id"], operation_iri))
        no_key_env = {
            key: value for key, value in os.environ.items() if key != "ONTOLOGY_MCP_API_KEY"
        }
        no_key = subprocess.run(
            ["uv", "run", "python", "-m", "app.mcp.server"],
            cwd=BACKEND,
            env=no_key_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert no_key.returncode != 0 and "ONTOLOGY_MCP_API_KEY is required" in no_key.stderr
    finally:
        if temporary_key_id:
            response = client.post(f"/api-keys/{temporary_key_id}:revoke")
            assert response.status_code == 200, response.text
        for project_id in reversed(created_projects):
            response = client.delete(f"/projects/{project_id}")
            assert response.status_code == 204, response.text
