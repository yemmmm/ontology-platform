"""Canonical, non-secret launch contract for Protocol's ontology-platform MCP."""

from __future__ import annotations

import json
from dataclasses import dataclass


# The frozen semantic mode is deliberately fixed rather than inherited from the host environment.
_CANONICAL_MODE_ENV = (
    ("SEMANTIC_CANONICAL_STORE", "rdf"),
    ("SEMANTIC_PRODUCT_WRITE_MODE", "rdf_primary"),
    ("SEMANTIC_READ_MODE", "canonical"),
)
_HARDENING_ENV = (
    ("PYTHONDONTWRITEBYTECODE", "1"),
    ("PYTHONNOUSERSITE", "1"),
    ("PYTHONUNBUFFERED", "1"),
)
_CONNECTION_ENV = (
    ("PYTHONPATH", "/agent/home/platform"),
    ("ONTOLOGY_MCP_BASE_URL", "http://127.0.0.1:8001"),
)
_REASONER_ENV = (
    ("SEMANTIC_REASONER_COMMAND", "/backend/scripts/dev_owl_reasoner.py"),
    ("PATH", "/backend/.venv/bin:/usr/bin:/bin"),
)


@dataclass(frozen=True)
class ProtocolMcpLaunchSpec:
    """Everything required to render the one permitted platform MCP block."""

    tools: tuple[str, ...]
    command: str = "/backend/.venv/bin/python"
    args: tuple[str, ...] = ("-m", "app.mcp.server")
    cwd: str = "/backend"
    canonical_mode_env: tuple[tuple[str, str], ...] = _CANONICAL_MODE_ENV
    hardening_env: tuple[tuple[str, str], ...] = _HARDENING_ENV
    reasoner_env: tuple[tuple[str, str], ...] = ()
    connection_env: tuple[tuple[str, str], ...] = _CONNECTION_ENV
    secret_env_name: str = "ONTOLOGY_MCP_API_KEY"

    def config_lines(self, *, api_key: str) -> list[str]:
        """Render the private config block without reading ambient environment state."""
        environment = (
            *self.canonical_mode_env,
            *self.hardening_env,
            *self.reasoner_env,
            *self.connection_env,
            (self.secret_env_name, api_key),
        )
        return [
            "[mcp_servers.ontology_platform]",
            f"command = {json.dumps(self.command)}",
            "args = [" + ", ".join(json.dumps(value) for value in self.args) + "]",
            f"cwd = {json.dumps(self.cwd)}",
            "required = true",
            "enabled_tools = [" + ", ".join(json.dumps(tool) for tool in self.tools) + "]",
            "[mcp_servers.ontology_platform.env]",
            *(f"{name} = {json.dumps(value)}" for name, value in environment),
        ]


def protocol_mcp_launch_spec(
    tools: frozenset[str], *, schema_version: int = 2
) -> ProtocolMcpLaunchSpec:
    """Build the stable launch specification from the frozen Protocol tool surface."""
    return ProtocolMcpLaunchSpec(
        tools=tuple(sorted(tools)),
        reasoner_env=_REASONER_ENV if schema_version == 2 else (),
    )


def canonical_protocol_mcp_mode_contract() -> dict[str, str]:
    """The baseline-bound, non-secret runtime portion of the MCP launch contract."""
    return dict(_CANONICAL_MODE_ENV)


def protocol_mcp_reasoner_contract() -> dict[str, str]:
    """The v2 Protocol-only non-secret reasoner child-environment contract."""
    return dict(_REASONER_ENV)
