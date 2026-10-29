"""Read-only, manifest-scoped MCP material access for bounded Agent execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations


def material_server(
    root: Path,
    workspace_config: Path | None = None,
    platform_config: Path | None = None,
    team_config: Path | None = None,
) -> FastMCP:
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
            "source_ranges": entry.get("source_ranges", []),
        }

    if workspace_config is not None:
        from ontoweave_modeling.workspace import WorkspaceRepository

        scope = json.loads(workspace_config.read_text(encoding="utf-8"))
        repository = WorkspaceRepository(scope["connection"], scope["schema"], scope["task_ref"])
        read_ids, write_ids = set(scope["read_ids"]), set(scope["write_ids"])
        if not write_ids.issubset(read_ids):
            raise ValueError("workspace write scope must also have explicit read permission")

        @server.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
            )
        )
        def read_workspace_object(object_id: str, revision: int | None = None) -> dict:
            """Read an authorized candidate business record or its exact revision."""
            if object_id not in read_ids:
                raise ToolError(json.dumps({"code": "forbidden", "recoverable": True}))
            result = repository.get(object_id, revision)
            return result or {
                "state": "not_found",
                "object_id": object_id,
                "authority": "candidate_workspace",
            }

        @server.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
            )
        )
        def put_workspace_object(
            object_id: str,
            kind: str,
            content: dict,
            expected_revision: int,
        ) -> dict:
            """Record candidate understanding with a baseline; this never applies or accepts a model."""
            if object_id not in write_ids:
                raise ToolError(json.dumps({"code": "forbidden", "recoverable": True}))
            return repository.put(object_id, kind, content, expected_revision)

    if platform_config is not None:
        platform = json.loads(platform_config.read_text(encoding="utf-8"))

        @server.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
            )
        )
        def query_semantic_context(
            queries: list[str], match_cursor: str | None = None, context_cursor: str | None = None
        ) -> dict:
            """Read the actual model in the Host-authorized scope. Page when completeness requires it."""
            body = {
                "project_id": platform["project_id"],
                "ontology_ids": platform["ontology_ids"],
                "scope_mode": "ontologies",
                "queries": queries,
                "search_mode": "lexical",
                "context_detail": "full",
                "limit": 20,
                "context_limit": 100,
                "match_cursor": match_cursor,
                "context_cursor": context_cursor,
            }
            request = urllib.request.Request(
                platform["base_url"] + "/api/semantic/context:query",
                data=json.dumps(body).encode(),
                method="POST",
                headers={
                    "Authorization": "Bearer " + platform["read_key"],
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    result = json.loads(response.read())
            except urllib.error.HTTPError as error:
                raise ToolError(
                    json.dumps(
                        {
                            "code": "platform_read_failed",
                            "recoverable": True,
                            "http_status": error.code,
                            "detail": json.loads(error.read()),
                        }
                    )
                ) from None
            expected = platform.get("model_revisions")
            if expected is not None:
                actual = {
                    row["ontology_id"]: row["model_revision"]
                    for row in result.get("scope", {}).get("ontologies", [])
                }
                if actual != expected:
                    raise ToolError(
                        json.dumps(
                            {
                                "code": "frozen_target_changed",
                                "recoverable": True,
                                "expected_revisions": expected,
                                "actual_revisions": actual,
                            }
                        )
                    )
            return result

    if team_config is not None:
        from .control import TaskControl
        from .team import TeamChannel, register_team_tools
        from .workspace import WorkspaceRepository

        scope = json.loads(team_config.read_text())
        repo = WorkspaceRepository(scope["connection"], scope["schema"], scope["task"]["task_ref"])
        if (
            scope["task"].get("collaboration")
            or scope["task"].get("work_units")
            or scope["task"].get("work_management")
        ):
            register_team_tools(
                server, TeamChannel(scope["task"], repo, TaskControl(repo), scope["actor"], root)
            )
        if scope["task"].get("work_units") or scope["task"].get("work_management"):
            from .work_plan import WorkPlan, register_work_tools

            register_work_tools(server, WorkPlan(scope["task"], repo, scope["actor"]))
        if scope["task"].get("shared_memory"):
            from .memory import SharedMemory, register_memory_tools

            register_memory_tools(server, SharedMemory(repo, scope["actor"]))
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workspace-config", type=Path)
    parser.add_argument("--platform-config", type=Path)
    parser.add_argument("--team-config", type=Path)
    args = parser.parse_args()
    material_server(args.root, args.workspace_config, args.platform_config, args.team_config).run(
        transport="stdio"
    )


if __name__ == "__main__":
    main()
