"""Evidence artifact MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool
from app.services import documents as artifact_service


def _chunk_page(rows: list[Any], artifact_id: str, offset: int, limit: int) -> dict[str, Any]:
    """Return a bounded, JSON-safe page of persisted evidence chunks."""
    if offset < 0:
        raise ValueError("offset must be greater than or equal to 0")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    return {
        "artifact_id": artifact_id,
        "document_id": artifact_id,
        "offset": offset,
        "limit": limit,
        "total": len(rows),
        "chunks": [
            {
                "id": row.id,
                "artifact_id": row.document_id,
                "document_id": row.document_id,
                "sequence": row.sequence,
                "parse_revision": row.parse_revision,
                "page_number": row.page_number,
                "char_start": row.char_start,
                "char_end": row.char_end,
                "text": row.text,
                "content_hash": row.content_hash,
            }
            for row in rows[offset : offset + limit]
        ],
    }


def register_documents(server: FastMCP) -> None:
    @server.tool()
    def list_evidence_artifacts(project_id: str) -> dict[str, Any]:
        """List uploaded evidence artifacts and deterministic parsing status."""
        return _run_tool(
            lambda session, _driver, _embedding_client: artifact_service.list_artifacts(
                session, project_id
            )
        )

    @server.tool()
    def get_evidence_artifact_status(artifact_id: str) -> dict[str, Any]:
        """Read parsing status, content identity, and chunk count for one evidence artifact."""
        return _run_tool(
            lambda session, _driver, _embedding_client: artifact_service.get_artifact(
                session, artifact_id
            )
        )

    @server.tool()
    def get_evidence_artifact_chunks(
        artifact_id: str, offset: int = 0, limit: int = 20
    ) -> dict[str, Any]:
        """Read exact chunk text, offsets, page, and hash for evidence construction."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _chunk_page(
                artifact_service.list_chunks(session, artifact_id),
                artifact_id,
                offset,
                limit,
            )
        )

    @server.tool()
    def list_source_documents(project_id: str) -> dict[str, Any]:
        """Compatibility alias for list_evidence_artifacts."""
        return _run_tool(
            lambda session, _driver, _embedding_client: artifact_service.list_artifacts(
                session, project_id
            )
        )

    @server.tool()
    def get_source_document_status(document_id: str) -> dict[str, Any]:
        """Compatibility alias for get_evidence_artifact_status."""
        return _run_tool(
            lambda session, _driver, _embedding_client: artifact_service.get_artifact(
                session, document_id
            )
        )

    @server.tool()
    def get_source_document_chunks(
        document_id: str, offset: int = 0, limit: int = 20
    ) -> dict[str, Any]:
        """Compatibility alias for get_evidence_artifact_chunks."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _chunk_page(
                artifact_service.list_chunks(session, document_id),
                document_id,
                offset,
                limit,
            )
        )
