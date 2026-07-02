"""Governance proposal MCP tools."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.schemas import ProposalCreate
from app.mcp.runtime import _run_tool
from app.services import governance as governance_service
from app.services.embedding import EmbeddingClient


def _parse_proposal_json(proposal_json: str) -> dict[str, Any]:
    """Parse the string transport used by models that cannot emit nested tool arguments."""
    try:
        proposal = json.loads(proposal_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"proposal_json must be valid JSON: {exc.msg}") from exc
    if not isinstance(proposal, dict):
        raise ValueError("proposal_json must decode to a JSON object")
    return proposal


def register_proposals(server: FastMCP) -> None:
    @server.tool()
    def submit_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
        """Submit an idempotent, version-scoped governance proposal; never writes formal data."""
        return _run_tool(
            lambda session, _driver, _embedding_client: governance_service.proposal_detail(
                session,
                governance_service.create_proposal(
                    session, ProposalCreate.model_validate(proposal)
                ).id,
            )
        )

    @server.tool()
    def submit_proposal_json(proposal_json: str) -> dict[str, Any]:
        """Submit a proposal encoded as JSON text when nested MCP arguments are unsupported."""
        proposal = _parse_proposal_json(proposal_json)
        return _run_tool(
            lambda session, _driver, _embedding_client: governance_service.proposal_detail(
                session,
                governance_service.create_proposal(
                    session, ProposalCreate.model_validate(proposal)
                ).id,
            )
        )

    @server.tool()
    def validate_proposal(proposal_id: str) -> dict[str, Any]:
        """Run deterministic validation for a proposed batch."""
        return _run_tool(
            lambda session, driver, _embedding_client: governance_service.proposal_detail(
                session,
                governance_service.validate_proposal(session, proposal_id, driver).id,
            )
        )

    @server.tool()
    def validate_draft(version_id: str) -> dict[str, Any]:
        """Validate every editable proposal for a draft and return deterministic results."""

        def validate(
            session: Session, driver: Driver, _embedding_client: EmbeddingClient
        ) -> Any:
            proposals = governance_service.list_version_proposals(session, version_id)
            results = []
            for proposal in proposals:
                if proposal.status == "proposed":
                    governance_service.validate_proposal(session, proposal.id, driver)
                detail = governance_service.proposal_detail(session, proposal.id)
                results.append(
                    {
                        "proposal_id": proposal.id,
                        "proposal_type": proposal.proposal_type,
                        "status": detail["status"],
                        "validation_result": detail["validation_result"],
                    }
                )
            return {"version_id": version_id, "proposals": results}

        return _run_tool(validate)

    @server.tool()
    def get_proposal_status(proposal_id: str) -> dict[str, Any]:
        """Read the complete proposal audit trail and evidence chain."""
        return _run_tool(
            lambda session, _driver, _embedding_client: governance_service.proposal_detail(
                session, proposal_id
            )
        )

    def _propose_knowledge(proposal: dict[str, Any], expected_type: str) -> dict[str, Any]:
        def create(
            session: Session, _driver: Driver, _embedding_client: EmbeddingClient
        ) -> Any:
            payload = ProposalCreate.model_validate(
                {**proposal, "proposal_type": expected_type}
            )
            created = governance_service.create_proposal(session, payload)
            return governance_service.proposal_detail(session, created.id)

        return _run_tool(create)

    @server.tool()
    def propose_schema_changes(proposal: dict[str, Any]) -> dict[str, Any]:
        """Submit a governed Schema candidate batch; never writes formal Schema directly."""
        return _propose_knowledge(proposal, "schema_change")

    @server.tool()
    def propose_entities(proposal: dict[str, Any]) -> dict[str, Any]:
        """Submit evidence-bound entity candidates; never merges or writes graph data directly."""
        return _propose_knowledge(proposal, "entity")

    @server.tool()
    def propose_relations(proposal: dict[str, Any]) -> dict[str, Any]:
        """Submit evidence-bound relation candidates against an existing RelationType."""
        return _propose_knowledge(proposal, "relation")

    @server.tool()
    def propose_entity_merges(proposal: dict[str, Any]) -> dict[str, Any]:
        """Submit possible duplicate entities for explicit human review; does not merge them."""
        return _propose_knowledge(proposal, "merge")

    @server.tool()
    def propose_rules(proposal: dict[str, Any]) -> dict[str, Any]:
        """Submit evidence-bound RuleDefinition candidates; never activates rules directly."""
        return _propose_knowledge(proposal, "rule")
