"""R2.3-008 start11: cursor-bound ``context_truncated`` is pagination, not loss.

In start11 issue-6 the governed lexical chain for required path
``currentlyConsumesOutput`` paginated: the first page's related context
exceeded ``context_limit``, so the platform emitted warning
``context_truncated`` together with a valid ``next_context_cursor``.  Protocol
consumed the continuation to a final non-truncated terminal page exactly as
its instructions require, but ``validate_ordinary_retrieval`` raised
``blocking warning: context_truncated`` on the first page, so the ordinary
retrieval receipt could never register and the acceptance handoff was
unreachable — an unfixable live-process failure.

The platform emits ``context_truncated`` exactly when the context page
carries a continuation cursor (``semantic_context_query`` builds the warning
from the same flag that publishes ``next_context_cursor``); that is the same
page-level pagination signal as ``matches_truncated``, which the gate already
skips.  Real truncation stays rejected twice over: the cursor-binding
invariant (``context_page.truncated`` must equal cursor presence) and the
terminal-page truncation check.  A terminal page that keeps the warning
without a cursor remains blocking.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modeling_team.acceptance import AcceptanceContractError, RunnerAcceptanceCarrier

from test_protocol_retrieval_gate import (
    _candidate,
    _carrier,
    _register_query,
    _result,
)


def _paginated_lexical_chain(carrier: RunnerAcceptanceCarrier, path: str) -> None:
    """The exact start11 shape: truncated first context page, then terminal."""

    _register_query(
        carrier,
        path,
        result=_result(
            path,
            next_context="context-1",
            warnings=[{"code": "context_truncated", "message": "Semantic context was truncated."}],
        ),
    )
    _register_query(
        carrier,
        path,
        context_cursor="context-1",
        result=_result(path),
    )


def test_cursor_bound_context_truncated_lexical_chain_registers(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    _paginated_lexical_chain(carrier, "invokesTool")
    receipt = carrier.validate_ordinary_retrieval()
    assert receipt["chains"][0]["statement_ids"] == ["statement-invokesTool"]
    assert len(receipt["chains"][0]["artifact_paths"]) == 2


def test_cursor_bound_context_truncated_hybrid_page_is_also_pagination(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    _register_query(
        carrier,
        "invokesTool",
        search_mode="hybrid",
        result=_result(
            "invokesTool",
            next_context="context-1",
            warnings=[{"code": "context_truncated", "message": "Semantic context was truncated."}],
        ),
    )
    _register_query(
        carrier,
        "invokesTool",
        search_mode="hybrid",
        context_cursor="context-1",
        result=_result("invokesTool"),
    )
    receipt = carrier.validate_ordinary_retrieval()
    assert receipt["chains"][0]["search_mode"] == "hybrid"


def test_terminal_context_truncated_warning_is_recorded_not_blocking(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    # A terminal page (no cursor) that still carries the warning may be real
    # loss.  R2.3-009 C-class: that judgment belongs to the independent
    # Examiner, so the chain completes and the warning is recorded.
    _register_query(
        carrier,
        "invokesTool",
        result=_result(
            "invokesTool",
            warnings=[{"code": "context_truncated", "message": "Semantic context was truncated."}],
        ),
    )
    receipt = carrier.validate_ordinary_retrieval()
    assert receipt["chains"][0]["statement_ids"] == ["statement-invokesTool"]
    assert (
        "retrieval response has blocking warning: context_truncated"
        in receipt["warnings_observed"]
    )
