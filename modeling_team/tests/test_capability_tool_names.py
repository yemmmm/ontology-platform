"""Model-visible capability tool names must stay within the codex name limit.

codex 0.148 renames any MCP tool whose model-visible name (the
``mcp__<server>__<operation>`` form) exceeds 64 bytes to an unstable
``<truncated>_<sha1-suffix>`` name.  A renamed capability is still callable,
but agents that identify capabilities by name (prompts, substring probes)
mis-read the rename as a missing capability — start10 of the R2.3-009 batch
stalled into run-fallback-timeout exactly this way.  Keep every advertised
operation short enough that its model-visible name is stable across codex
versions.
"""

from __future__ import annotations

from modeling_team.capability_mcp import (
    CAPABILITY_TOOL_SCHEMAS,
    PROTOCOL_OPERATIONS,
    ROLE_OPERATIONS,
    STAGED_UNIFIED_PROTOCOL_OPERATIONS,
    UNIFIED_PROTOCOL_OPERATIONS,
    UNIFIED_PROTOCOL_RUN_OPERATIONS,
)

# ``mcp__`` + server name + ``__`` + operation, as constructed by codex.
MODEL_VISIBLE_PREFIX = "mcp__runner_capability__"
MODEL_VISIBLE_NAME_LIMIT = 64


def test_every_role_operation_has_a_stable_model_visible_name() -> None:
    advertised = {
        operation
        for operations in ROLE_OPERATIONS.values()
        for operation in operations
    }
    assert advertised, "ROLE_OPERATIONS must advertise at least one operation"
    for operation in sorted(advertised):
        model_name = MODEL_VISIBLE_PREFIX + operation
        assert len(model_name) <= MODEL_VISIBLE_NAME_LIMIT, (
            f"{operation!r} renders as a {len(model_name)}-char model-visible "
            f"name {model_name!r}; codex would rename it to an unstable "
            "truncated+hashed name. Shorten the operation name."
        )


def test_every_advertised_operation_has_a_schema() -> None:
    advertised = {
        operation
        for operations in ROLE_OPERATIONS.values()
        for operation in operations
    }
    assert advertised == set(CAPABILITY_TOOL_SCHEMAS), (
        "ROLE_OPERATIONS and CAPABILITY_TOOL_SCHEMAS must stay in sync"
    )


def test_staged_unified_surface_keeps_the_association_catalog_advertised() -> None:
    # R4.0-024: ``protocol_inspect_associations`` resolves read refs only from
    # Runner-observed platform records, so the staged unified run surface must
    # also advertise the pre-existing catalog read that publishes those
    # observed artifact identities.  The tuple stays duplicate-free and the
    # formal protocol assembly (PROTOCOL_OPERATIONS first) never lists one
    # operation twice.
    assert STAGED_UNIFIED_PROTOCOL_OPERATIONS == (
        *UNIFIED_PROTOCOL_RUN_OPERATIONS,
        "protocol_list_platform_artifacts",
    )
    assert "protocol_inspect_associations" in STAGED_UNIFIED_PROTOCOL_OPERATIONS
    assert len(set(STAGED_UNIFIED_PROTOCOL_OPERATIONS)) == len(
        STAGED_UNIFIED_PROTOCOL_OPERATIONS
    )
    assert UNIFIED_PROTOCOL_OPERATIONS == (*PROTOCOL_OPERATIONS, *UNIFIED_PROTOCOL_RUN_OPERATIONS)
    assert len(set(UNIFIED_PROTOCOL_OPERATIONS)) == len(UNIFIED_PROTOCOL_OPERATIONS)
    assert ROLE_OPERATIONS["protocol"] == UNIFIED_PROTOCOL_OPERATIONS
