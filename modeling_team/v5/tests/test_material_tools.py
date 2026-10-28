import asyncio
import hashlib
import json

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
