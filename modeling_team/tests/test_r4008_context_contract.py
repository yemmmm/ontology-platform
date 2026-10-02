from pathlib import Path

from modeling_team.protocol_retrieval_gate import ProtocolRetrievalGate
from modeling_team.modeling_readonly import ModelingReadProxy
from modeling_team.read_proxy_mcp import _MODELING_TOOL_SCHEMAS
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.acceptance_runtime import _EXAMINER_TOOL_FIELDS


def test_optional_roles_are_frozen_without_requiring_legacy_requests_to_send_them():
    base = {
        "query": "q",
        "project_id": "p",
        "scope_mode": "ontologies",
        "ontology_ids": ["o"],
        "resource_types": ["fact"],
        "assertion_types": ["asserted"],
        "search_mode": "lexical",
        "depth": 1,
        "limit": 1,
        "context_limit": 1,
    }
    plain = ProtocolRetrievalGate._frozen_key(base)
    assert plain == ProtocolRetrievalGate._frozen_key({**base, "semantic_roles": None})
    filtered = ProtocolRetrievalGate._frozen_key(
        {**base, "semantic_roles": ["Action", " Rule ", "Action"]}
    )
    assert filtered != plain
    assert filtered == ProtocolRetrievalGate._frozen_key(
        {**base, "semantic_roles": ["Rule", "Action"]}
    )


def test_modeling_proxy_accepts_roles_projection_and_zero_expansion():
    calls = []
    proxy = ModelingReadProxy(
        socket_path=Path("/tmp/r4008-policy-test.sock"),
        token="token",
        read_key="key",
        project_id="p",
        ontology_id="o",
        forward=lambda tool, arguments, key: calls.append(arguments) or {"ok": True, "data": {}},
    )
    result = proxy.handle(
        {
            "token": "token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {
                "project_id": "p",
                "scope_mode": "ontologies",
                "ontology_ids": ["o"],
                "queries": ["example"],
                "semantic_roles": ["Action"],
                "context_detail": "full",
                "depth": 0,
                "context_limit": 0,
            },
        }
    )
    assert result["ok"] is True
    assert calls[0]["semantic_roles"] == ["Action"]
    assert calls[0]["context_detail"] == "full"
    properties = _MODELING_TOOL_SCHEMAS["query_semantic_context"]["inputSchema"]["properties"]
    assert "semantic_roles" in properties
    assert "context_detail" in properties
    assert "semantic_roles" in _EXAMINER_TOOL_FIELDS["query_semantic_context"]


def test_partial_expansion_does_not_pass_generic_complete_even_without_a_warning():
    adapter = object.__new__(CodexRuntimeAdapter)
    data = {
        "result_status": "matched",
        "recall": {"completeness": "complete"},
        "truncated": False,
        "matches_page": {"truncated": False, "next_match_cursor": None},
        "context_page": {
            "truncated": False,
            "next_context_cursor": None,
            "expansion": {"status": "partial"},
        },
        "primary_matches": [{"ontology_id": "o", "warnings": []}],
        "related_context": [],
        "warnings": [],
    }
    assert adapter._complete_generic_retrieval({"ok": True, "data": data}, ["o"]) is False
