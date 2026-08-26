"""MCP tools for Protection Set management (R3.0-004 §10.2)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool, get_resources, runtime_principal
from app.security.auth import audit_security_event
from app.services.semantic_protection_set import SemanticProtectionSetService


def _audit(event_type: str, project_id: str | None, set_id: str, name: str, **details: Any) -> None:
    session_factory, _driver, _embedding = get_resources()
    audit_security_event(
        session_factory,
        event_type,
        "success",
        runtime_principal(),
        project_id=project_id,
        resource_type="semantic_protection_set",
        resource_id=set_id,
        details={"name": name, **details},
    )


def register_protection_sets(server: FastMCP) -> None:
    @server.tool()
    def list_semantic_protection_sets(project_id: str) -> dict[str, Any]:
        """List the protection sets of one authorized Project."""
        return _run_tool(
            lambda session, _driver, _embedding: SemanticProtectionSetService(
                session
            ).list_sets(project_id)
        )

    @server.tool()
    def create_semantic_protection_set(
        project_id: str,
        name: str,
        description: str | None = None,
        allowed_grants: list[str] | None = None,
        members: list[dict[str, Any]] | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Create a protection set (named resource IRIs + OR-semantics grants)."""
        def _create(session, _driver, _embedding):
            result = SemanticProtectionSetService(session).create_set(
                project_id=project_id,
                name=name,
                description=description,
                allowed_grants=allowed_grants,
                members=members or [],
            )
            _audit(
                "semantic_protection_set_created",
                project_id,
                result["id"],
                result["name"],
                member_count=result["member_count"],
            )
            result.pop("members_added", None)
            return result

        return _run_tool(_create)

    @server.tool()
    def update_semantic_protection_set(
        protection_set_id: str,
        name: str | None = None,
        description: str | None = None,
        allowed_grants: list[str] | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Update a protection set name, description, or allowed_grants."""
        def _update(session, _driver, _embedding):
            result = SemanticProtectionSetService(session).update_set(
                protection_set_id,
                name=name,
                description=description,
                allowed_grants=allowed_grants,
            )
            _audit(
                "semantic_protection_set_updated",
                result["project_id"],
                protection_set_id,
                result["name"],
                allowed_grants=result["allowed_grants"],
                member_count=result["member_count"],
            )
            return result

        return _run_tool(_update)

    @server.tool()
    def delete_semantic_protection_set(protection_set_id: str, actor: str | None = None) -> dict[str, Any]:
        """Delete an empty protection set; non-empty sets are rejected."""
        def _delete(session, _driver, _embedding):
            service = SemanticProtectionSetService(session)
            detail = service.get_set(protection_set_id)
            service.delete_set(protection_set_id)
            _audit(
                "semantic_protection_set_deleted",
                detail["project_id"],
                protection_set_id,
                detail["name"],
            )
            return {"id": protection_set_id, "deleted": True}

        return _run_tool(_delete)

    @server.tool()
    def add_semantic_protection_set_members(
        protection_set_id: str,
        members: list[dict[str, Any]],
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Batch-add resource IRIs to a protection set (idempotent)."""
        def _add(session, _driver, _embedding):
            service = SemanticProtectionSetService(session)
            result = service.add_members(protection_set_id, members)
            detail = service.get_set(protection_set_id)
            _audit(
                "semantic_protection_set_members_added",
                detail["project_id"],
                protection_set_id,
                detail["name"],
                member_count=result["member_count"],
            )
            return result

        return _run_tool(_add)

    @server.tool()
    def remove_semantic_protection_set_members(
        protection_set_id: str,
        resource_iris: list[str],
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Batch-remove resource IRIs from a protection set."""
        def _remove(session, _driver, _embedding):
            service = SemanticProtectionSetService(session)
            result = service.remove_members(protection_set_id, resource_iris)
            detail = service.get_set(protection_set_id)
            _audit(
                "semantic_protection_set_members_removed",
                detail["project_id"],
                protection_set_id,
                detail["name"],
                member_count=result["member_count"],
            )
            return result

        return _run_tool(_remove)
