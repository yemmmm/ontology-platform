from __future__ import annotations

import threading
from types import SimpleNamespace
from pathlib import Path

from modeling_team.protocol_retrieval_gate import ORDINARY_RETRIEVAL_RECEIPT_SCHEMA
from modeling_team.runtimes.codex import CodexRuntimeAdapter


def _adapter_with_agent(*, receipt: bool) -> CodexRuntimeAdapter:
    adapter = CodexRuntimeAdapter(repository_root=Path.cwd(), use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._acceptance = SimpleNamespace(
        ordinary_retrieval_receipt=(
            {"schema_version": ORDINARY_RETRIEVAL_RECEIPT_SCHEMA} if receipt else None
        )
    )
    agent = SimpleNamespace(
        agent_id="protocol",
        fallback_eligible=True,
        retrieval_episode=1,
        retrieval_state="fallback_required",
        io_lock=threading.RLock(),
        state_lock=threading.RLock(),
    )
    adapter.agents["protocol"] = agent
    return adapter


def test_host_receipt_allows_terminal_after_legacy_warning_fallback() -> None:
    adapter = _adapter_with_agent(receipt=True)
    assert adapter.terminal_report_blocked("protocol", already_synchronized=True) is False


def test_missing_host_receipt_keeps_legacy_fallback_block() -> None:
    adapter = _adapter_with_agent(receipt=False)
    assert adapter.terminal_report_blocked("protocol", already_synchronized=True) is True


def test_host_receipt_is_authoritative_for_query_state() -> None:
    adapter = _adapter_with_agent(receipt=True)
    agent = adapter.agents["protocol"]
    item = {
        "status": "completed",
        "arguments": {
            "scope_mode": "ontologies",
            "ontology_ids": ["ontology-1"],
        },
        "result": {
            "structuredContent": {
                "ok": True,
                "data": {
                    "result_status": "matched",
                    "recall": {"completeness": "degraded"},
                    "truncated": False,
                    "matches_page": {"truncated": False, "next_match_cursor": None},
                    "context_page": {"truncated": False, "next_context_cursor": None},
                    "warnings": [{"code": "vector_index_missing"}],
                    "primary_matches": [],
                    "related_context": [],
                },
            }
        },
    }
    adapter._complete_retrieval_query(agent, item)
    assert agent.retrieval_state == "complete"
