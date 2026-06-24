"""Source document MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool
from app.services import documents as document_service


def _chunk_page(rows: list[Any], document_id: str, offset: int, limit: int) -> dict[str, Any]:
    """Return a bounded, JSON-safe page of persisted source chunks."""
    if offset < 0:
        raise ValueError("offset must be greater than or equal to 0")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    return {
        "document_id": document_id,
        "offset": offset,
        "limit": limit,
        "total": len(rows),
        "chunks": [
            {
                "id": row.id,
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
    def list_source_documents(project_id: str) -> dict[str, Any]:
        """List uploaded sources and their deterministic parsing status."""
        return _run_tool(
            lambda session, _driver, _embedding_client: document_service.list_documents(
                session, project_id
            )
        )

    @server.tool()
    def get_source_document_status(document_id: str) -> dict[str, Any]:
        """Read parsing status, content identity, and chunk count for one source."""
        return _run_tool(
            lambda session, _driver, _embedding_client: document_service.get_document(
                session, document_id
            )
        )

    @server.tool()
    def get_source_document_chunks(
        document_id: str, offset: int = 0, limit: int = 20
    ) -> dict[str, Any]:
        """Read exact persisted chunk text, offsets, page, and chunk hash for Evidence."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _chunk_page(
                document_service.list_chunks(session, document_id),
                document_id,
                offset,
                limit,
            )
        )
