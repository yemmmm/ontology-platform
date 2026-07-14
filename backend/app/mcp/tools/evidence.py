"""MCP tools for lightweight project evidence references."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool
from app.services.evidence_reference import (
    EvidenceReferenceService,
    association_to_dict,
    reference_to_dict,
)


def register_evidence(server: FastMCP) -> None:
    @server.tool()
    def create_evidence_reference(
        project_id: str,
        document_name: str,
        excerpt: str,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Create or idempotently reuse a project evidence reference."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _create(
                session, project_id, document_name, excerpt, actor
            )
        )

    @server.tool()
    def list_evidence_references(
        project_id: str,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List project evidence references without loading complete source documents."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _list(
                session, project_id, search, limit, offset
            )
        )

    @server.tool()
    def get_evidence_reference(reference_id: str) -> dict[str, Any]:
        """Read one evidence reference and its modeling-result associations."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _get(session, reference_id)
        )

    @server.tool()
    def associate_evidence_reference(
        project_id: str,
        ontology_id: str,
        target_type: str,
        target_id: str,
        evidence_reference_ids: list[str] | None = None,
        evidence: list[dict[str, str]] | None = None,
        graph_set_id: str | None = None,
        client_item_id: str | None = None,
        edit_audit_id: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Create or reuse references and associate them with one concrete modeling result."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _associate(
                session,
                project_id=project_id,
                ontology_id=ontology_id,
                target_type=target_type,
                target_id=target_id,
                evidence_reference_ids=evidence_reference_ids or [],
                evidence=evidence or [],
                graph_set_id=graph_set_id,
                client_item_id=client_item_id,
                edit_audit_id=edit_audit_id,
                actor=actor,
            )
        )


def _create(session, project_id: str, document_name: str, excerpt: str, actor: str | None):
    service = EvidenceReferenceService(session)
    row, created = service.get_or_create(project_id, document_name, excerpt, actor=actor)
    session.commit()
    return {**reference_to_dict(row), "created": created}


def _list(session, project_id: str, search: str | None, limit: int, offset: int):
    if limit < 1 or limit > 200 or offset < 0:
        raise ValueError("limit must be 1..200 and offset must be non-negative")
    rows, total = EvidenceReferenceService(session).list_references(
        project_id, search=search, limit=limit, offset=offset
    )
    return {"items": [reference_to_dict(row) for row in rows], "total": total}


def _get(session, reference_id: str):
    service = EvidenceReferenceService(session)
    row = service.get(reference_id)
    associations = service.list_associations(reference_id=reference_id)
    return {
        **reference_to_dict(row, association_count=len(associations)),
        "associations": [association_to_dict(item) for item in associations],
    }


def _associate(session, **payload):
    service = EvidenceReferenceService(session)
    resolved = service.resolve_candidates(
        payload["project_id"],
        reference_ids=payload["evidence_reference_ids"],
        inline_evidence=payload["evidence"],
        actor=payload["actor"],
        persist=True,
    )
    rows = service.associate(
        project_id=payload["project_id"],
        ontology_id=payload["ontology_id"],
        graph_set_id=payload["graph_set_id"],
        target_type=payload["target_type"],
        target_id=payload["target_id"],
        client_item_id=payload["client_item_id"],
        edit_audit_id=payload["edit_audit_id"],
        references=[row for row, _candidate, _created in resolved if row is not None],
        actor=payload["actor"],
    )
    session.commit()
    return {"items": [association_to_dict(row) for row in rows], "total": len(rows)}
