import asyncio
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from ontoweave_modeling.material_tools import material_server


def fixture_server(tmp_path):
    payload = b"Approved engineering material with an explicit exception."
    (tmp_path / "source.md").write_bytes(payload)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "source": {
                    "path": "source.md",
                    "source_ref": "fixture-source-v1",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            }
        )
    )
    return material_server(tmp_path), payload


def test_material_ranges_preserve_version_and_exact_source(tmp_path):
    server, payload = fixture_server(tmp_path)
    response = asyncio.run(
        server.call_tool(
            "read_material",
            {
                "material_id": "source",
                "offset": 9,
                "limit": 11,
            },
        )
    )
    actual = json.loads(response[0].text)
    assert actual["text"] == payload.decode()[9:20]
    assert actual["sha256"] == hashlib.sha256(payload).hexdigest()
    assert actual["next_offset"] == 20
    assert actual["source_ref"] == "fixture-source-v1"


@pytest.mark.parametrize("material_id", ["hidden-evaluation", "../private", "/etc/passwd"])
def test_unknown_and_outside_materials_return_recoverable_error(tmp_path, material_id):
    server, _ = fixture_server(tmp_path)
    with pytest.raises(ToolError, match="material_not_found"):
        asyncio.run(server.call_tool("read_material", {"material_id": material_id}))


def test_changed_source_is_not_silently_read_as_frozen_revision(tmp_path):
    server, _ = fixture_server(tmp_path)
    (tmp_path / "source.md").write_text("Changed material.")
    with pytest.raises(ToolError, match="source_revision_changed"):
        asyncio.run(server.call_tool("read_material", {"material_id": "source"}))


@pytest.mark.parametrize("actual_revision", [2, 3])
def test_governed_read_preserves_authorized_scope_and_frozen_revision(tmp_path, actual_revision):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "scope": {
                            "ontologies": [
                                {
                                    "ontology_id": "approved-ontology",
                                    "model_revision": actual_revision,
                                }
                            ]
                        }
                    }
                ).encode()
            )

        def log_message(self, *_):
            pass

    endpoint = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=endpoint.serve_forever, daemon=True)
    thread.start()
    try:
        (tmp_path / "manifest.json").write_text("{}")
        config = tmp_path / "platform.json"
        config.write_text(
            json.dumps(
                {
                    "base_url": f"http://127.0.0.1:{endpoint.server_port}",
                    "read_key": "engineering-read-only-key",
                    "project_id": "approved-project",
                    "ontology_ids": ["approved-ontology"],
                    "model_revisions": {"approved-ontology": 2},
                }
            )
        )
        server = material_server(tmp_path, platform_config=config)
        if actual_revision == 2:
            result = asyncio.run(
                server.call_tool("query_semantic_context", {"queries": ["definition"]})
            )
            assert json.loads(result[0].text)["scope"]["ontologies"][0]["model_revision"] == 2
        else:
            with pytest.raises(ToolError, match="frozen_target_changed"):
                asyncio.run(server.call_tool("query_semantic_context", {"queries": ["definition"]}))
        assert received[0]["project_id"] == "approved-project"
        assert received[0]["ontology_ids"] == ["approved-ontology"]
        assert received[0]["scope_mode"] == "ontologies"
    finally:
        endpoint.shutdown()
        endpoint.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("actual_revision", [2, 3])
@pytest.mark.parametrize(
    "family",
    [
        "relation-type-list",
        "table-mapping-detail",
        "join-mapping-detail",
        "operation-detail",
        "resource-relations",
    ],
)
def test_exact_resource_read_uses_scoped_key_and_checks_revision(tmp_path, actual_revision, family):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"model_revision": actual_revision, "items": [{"iri": "urn:test"}]}
                ).encode()
            )

        def log_message(self, *_):
            pass

    endpoint = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=endpoint.serve_forever, daemon=True)
    thread.start()
    try:
        (tmp_path / "manifest.json").write_text("{}")
        config = tmp_path / "platform.json"
        config.write_text(
            json.dumps(
                {
                    "base_url": f"http://127.0.0.1:{endpoint.server_port}",
                    "read_key": "scoped-read-key",
                    "project_id": "project",
                    "ontology_ids": ["ontology"],
                    "model_revisions": {"ontology": 2},
                }
            )
        )
        server = material_server(tmp_path, platform_config=config)
        arguments = {
            "ontology_id": "ontology",
            "resource_iri": "urn:test",
            "family": family,
        }
        if actual_revision == 2:
            response = asyncio.run(server.call_tool("read_model_resource", arguments))
            assert json.loads(response[0].text)["items"][0]["iri"] == "urn:test"
        else:
            with pytest.raises(ToolError, match="frozen_target_changed"):
                asyncio.run(server.call_tool("read_model_resource", arguments))
        with pytest.raises(ToolError, match="resource_scope_forbidden"):
            asyncio.run(
                server.call_tool("read_model_resource", {**arguments, "ontology_id": "other"})
            )
        assert len(received) == 1
        assert received[0] == (
            f"/api/semantic/ontologies/ontology/read-models/{family}?entity=urn%3Atest&field_set=detail",
            "Bearer scoped-read-key",
        )
    finally:
        endpoint.shutdown()
        endpoint.server_close()
        thread.join(timeout=5)
