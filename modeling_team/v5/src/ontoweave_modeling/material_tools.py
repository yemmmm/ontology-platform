"""Read-only, manifest-scoped MCP material access for bounded Agent execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations


def material_server(root: Path) -> FastMCP:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    server = FastMCP("ontoweave-materials")

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def read_material(material_id: str, offset: int = 0, limit: int = 12000) -> dict:
        """Read authorized source text by ID and character offset. Unknown IDs are recoverable."""
        if material_id not in manifest:
            raise ToolError(
                json.dumps(
                    {
                        "code": "material_not_found",
                        "recoverable": True,
                        "material_id": material_id,
                        "available_ids": sorted(manifest),
                    }
                )
            )
        if offset < 0 or limit <= 0:
            raise ToolError(json.dumps({"code": "invalid_range", "recoverable": True}))
        entry = manifest[material_id]
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ToolError(json.dumps({"code": "material_forbidden", "recoverable": True}))
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != entry["sha256"]:
            raise ToolError(json.dumps({"code": "source_revision_changed", "recoverable": True}))
        text = payload.decode("utf-8")
        end = min(len(text), offset + limit)
        return {
            "material_id": material_id,
            "source_ref": entry["source_ref"],
            "sha256": digest,
            "offset": offset,
            "next_offset": end if end < len(text) else None,
            "total_characters": len(text),
            "text": text[offset:end],
        }

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    material_server(args.root).run(transport="stdio")


if __name__ == "__main__":
    main()
